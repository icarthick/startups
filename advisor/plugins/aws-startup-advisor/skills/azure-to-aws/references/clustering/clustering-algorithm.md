# Clustering — resource-group seed, then split and merge

Loaded by `discover-assemble.md`. Produces `azure-resource-clusters.json` per
`references/shared/schema-discover-azure.md`.

## Why not just use resource groups

A resource group is a **filing decision**, not an architectural one, and Azure estates
file four different ways:

| RG layout                                          | Does RG-only clustering work?                                 |
| -------------------------------------------------- | ------------------------------------------------------------- |
| one app per group                                  | yes                                                           |
| one group per environment, several apps            | **no** — splits nothing; one cluster holds unrelated workloads |
| horizontal groups by type (`rg-data`, `rg-app`)    | **no** — actively separates an app from its own database       |
| one group for everything (the startup default)     | **no signal at all**                                          |

So the group is a good **seed** and a bad final answer. The point of clustering is to
make the recommendation describe *workloads*; a cluster that is really just a filing
folder produces a report that reads like 40 unrelated rows with extra steps.

**Azure's edge data is richer than GCP's and does not require IaC.** GCP's graph comes
from Terraform reference expressions, so it exists only when IaC does. Azure embeds full
ARM resource IDs inside resource *properties*, so `hosted_on`, `network`, `private_link`,
`secret_ref`, `data_ref`, and `identity_grant` all survive a live capture or an RDfA
archive. That is what makes refinement worth doing here.

## The algorithm

### Step 1 — Seed

One candidate cluster per distinct `resource_group` across `resources[]`. A resource with
`resource_group: null` (it carries a `resource_group_unresolved` warning) goes straight to
`unclustered[]` — do not invent a group for it.

Resources whose type is a Skip Mapping still cluster. They are part of the workload's
shape even when they get no AWS target, and excluding them would make the cluster's
member list disagree with the inventory, which the phase's accounting assert catches.

### Step 2 — Split a seed with no internal edges

For each candidate, build the subgraph of edges **between its own members** (ignore edges
leaving the cluster). If that subgraph has more than one connected component, the
candidate is not one workload — split it into one cluster per component.

Set `justification: "split:no_internal_edges"` on each resulting cluster, and put the
crossing evidence in `edges[]`.

**A component of one resource is legal**, and common: a lone storage account in a shared
group has no edges because nothing references it. Do not merge singletons together just
to avoid small clusters — "these two resources share a filing folder and nothing else" is
exactly the false grouping this step exists to break.

> **Direction is ignored for connectivity.** An app referencing a database and a database
> being referenced by an app are the same relationship. Treat every edge as undirected
> when computing components; direction matters only for tiering and for the report's
> phrasing.

### Step 3 — Merge candidates joined by crossing edges

For each edge whose source and target are in **different** candidates, merge those two
candidates. Repeat to a fixed point — merging is transitive, so an app in `rg-app`
referencing a database in `rg-data` which references a vault in `rg-shared` yields one
cluster of three.

Set `justification: "merge:cross_group_edges"`, and `edges[]` **must** contain the
crossing edges that caused it. A merge whose justification cannot be shown is a merge the
user cannot validate on the Clarify assumption sheet.

**Not every edge type should merge.** Two edge types are *ambient* — they connect almost
everything to a small number of shared resources, so merging on them collapses the whole
estate into one cluster and destroys the partition:

| Edge type            | Merges? | Why                                                                                              |
| -------------------- | ------- | ------------------------------------------------------------------------------------------------ |
| `hosted_on`          | **yes** | the strongest edge there is — an app and its plan are one compute unit                            |
| `data_ref`           | **yes** | an app and the database it addresses are one workload                                             |
| `private_link`       | **yes** | an explicit, deliberately-created app-to-data path                                                |
| `declared_affinity`  | **yes** | the customer said so; declared intent outranks inference                                          |
| `identity_grant`     | **yes** | "app X reads storage Y" is a real dependency, and Azure exposes it more cleanly than GCP          |
| `network`            | **no**  | every workload in a VNet shares subnets. A shared subnet is colocation, not relatedness           |
| `secret_ref`         | **no**  | one Key Vault typically serves the entire estate; merging on it produces one cluster              |

A non-merging edge is still **recorded** on the resource and still counts for Step 2's
internal connectivity — it just does not pull two candidates together. That asymmetry is
deliberate: sharing a subnet is weak evidence of relatedness but perfectly good evidence
that two already-related resources belong in the same cluster.

### Step 4 — Assign identity, tier, and primary

Per cluster: `cluster_id`, `tier` (see `tiering.md`), `primary` and member
classification (see `classification-rules.md`), and the `pattern_id` /
`pattern_status` fields (`patterns.md`, build step 4 — until it exists, every cluster is
`pattern_id: "unclassified"` with `pattern_status: "catalog_absent"`).

**`cluster_id` must be stable across runs of the same repo**, because Clarify records the
user's pattern confirmation against it and a re-run must not orphan those answers. Derive
it from the cluster's `primary` resource — `<resource-group>-<primary-name>` slugified —
and never from iteration order or an incrementing counter.

### Step 5 — Verify before writing

- Every inventory resource is a member of exactly one cluster, or is in `unclustered[]`.
- No resource appears in two clusters (merging must union members, not duplicate them).
- Every `justification` of `edges`, `split:*`, or `merge:*` has a non-empty `edges[]`.
- Every `azure_id` in `edges[]` and `members[]` exists in the inventory.

## Worked example

Given: `rg-app` {plan, 5 web apps, storage, vault, vnet, 2 subnets}, `rg-data`
{postgres, redis, cosmos, eventhub, private endpoint}, `rg-shared` {idle plan, Windows
VM, NIC}.

1. **Seed** → 3 candidates.
2. **Split** — `rg-shared`'s VM+NIC are joined by a `network` edge; the idle plan has no
   edges at all. Two components → **split** into `{VM, NIC}` and `{idle plan}`.
3. **Merge** — a web app has a `data_ref` to the postgres server, and the private endpoint
   has a `private_link` to it. `rg-app` and `rg-data` **merge**. The subnet `network`
   edges do not merge anything (they are ambient) but are recorded.
4. Result: **3 clusters** — the merged app+data workload, the VM, and the idle plan.

Note what each step bought: the split stopped the idle plan being reported as part of a
reporting-VM workload, and the merge stopped the app being costed without its database.
Neither is visible from resource groups alone.

## Status — build step 4

Implemented. `patterns.md` and the cluster-level `data-pipeline` gate are the remaining
step-4 items; until `patterns.md` exists every cluster carries
`pattern_status: "catalog_absent"`, which is a defined state and not a gap
(`schema-design-aws.md` § clusters).
