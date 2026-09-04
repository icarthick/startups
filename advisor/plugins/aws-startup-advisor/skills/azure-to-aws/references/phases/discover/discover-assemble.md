---
_assemble: assemble-inventory
_of_phase: discover
_reads:
  - iac (fragment contribution)
_produces:
  - azure-resource-inventory.json
  - azure-resource-clusters.json
_knowledge:
  - { file: references/shared/schema-discover-azure.md }
---

# Discover — Assemble Inventory and Clusters

> **Assembler unit.** Runs after the discover fragments have written their
> contributions. It is the single creator of both phase artifacts and owns their
> final contract. See `discover.md` for how it is composed into the phase.

**Schema reference**: `references/shared/schema-discover-azure.md` — consult for
complete field definitions, per-type `config` schemas, the drift record shape, and
the validation checklist.

## Assembly rules

1. Merge every fragment's contributions into `resources[]`, keyed by `azure_id`.
   One entry per `azure_id`; never two.
2. Each entry carries at minimum `azure_id`, `azure_type` (canonical `Microsoft.*`),
   `resource_group`, `subscription_id`, `source`, and `config`.
3. Write `metadata`: `discovery_timestamp`, `discovery_sources` (only sources that
   actually contributed), `subscriptions_discovered`, `total_resources`, and
   `confidence`.
4. Apply source precedence when two sources describe the same `azure_id`, highest
   first: **live `az`** (current existence and configuration — it is *now*), then
   **RDfA** (utilization, reservations, consumption; loses to live on state because
   an archive may be days old, wins on measurement because live has no rollup), then
   **IaC** (authoritative for provenance, module structure, and declared-but-
   undeployed resources; authoritative for nothing about state), then **billing**
   (fallback only, `billing_inferred`).
5. **Every disagreement becomes a drift entry.** Record both values, both sources,
   and which won, so the report can say "your Terraform declares `Standard_D2s_v3`,
   your tenant is running `Standard_D4s_v3`" instead of quietly picking one.
6. Derive `azure-resource-clusters.json`.

## Confidence vocabulary

Four tiers, set per resource and per mapping decision:

| Label              | Meaning                                                    | Source                                              |
| ------------------ | ---------------------------------------------------------- | --------------------------------------------------- |
| `deterministic`    | fixed 1:1 table lookup                                     | the fast-path Direct Mappings table                 |
| `measured`         | rubric backed by observed utilization, not declared config  | RDfA 31-day rollup **or** `az monitor metrics list` |
| `inferred`         | rubric from declared config only                           | IaC, or live CLI without metrics                    |
| `billing_inferred` | billing-only fallback                                      | Cost Management export                              |

`measured` is deliberately not named after one tool. Naming it `rdfa_inferred` would
mean the live path could never earn the tier even when it supplies the same
evidence. User-facing label: **"Measured from your actual usage."**

## Status — skeleton (build step 1)

Writes both artifacts from the single IaC fragment. `azure-resource-clusters.json`
is emitted with one cluster per resource group and an empty `edges[]` — a seed with
no refinement.

| Lands in | What                                                                                                    |
| -------- | ------------------------------------------------------------------------------------------------------- |
| step 2   | The merge-and-drift rules above, exercised once more than one source can contribute                     |
| step 4   | Real clustering: resource-group seed, then split candidates with no internal edges and merge candidates whose edges cross group boundaries; fixed tiering; `pattern_id` + `pattern_confidence` |

**Resource group is a good seed and a bad final answer.** It works when there is one
app per group; it splits nothing when there is one group per environment; it actively
separates things that belong together under horizontal groups (`rg-databases`,
`rg-app`); and it carries no signal at all in the single-group startup default. The
refinement is what makes clustering mean anything.

Azure's edge data is richer than GCP's and does not require IaC: ARM resource IDs
are embedded in resource *properties*, so edges survive every discovery source —
`serverFarmId` on a web app, `subnetId`, a private endpoint's `privateLinkServiceId`,
a Key Vault reference in app settings, a managed identity plus its role-assignment
scope, and `app=` / `workload=` tags.

## Step: Assemble

1. Apply the assembly rules above.
2. Validate both artifacts against `schema-discover-azure.md`'s checklist.
3. If no valid resources came from any source after the fragments ran, stop with a
   diagnostic naming which sources were attempted. Do not write an empty inventory
   to satisfy the gate.
