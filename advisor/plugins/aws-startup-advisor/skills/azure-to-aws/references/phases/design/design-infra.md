---
_fragment: infra
_of_phase: design
_contributes:
  - aws-design.json (services[], clusters[], deferred[], warnings[])
---

# Design — Infrastructure Mapping

> **Fragment unit.** See `design.md` for how it is composed into the phase.

Runs the two-pass mapping engine over the clustered inventory: pass 1 is the
disposition table, pass 2 is the category rubric. It applies the precedence order in
`design.md` and never reorders it.

## What to load

| File                                          | When                                                    |
| --------------------------------------------- | ------------------------------------------------------- |
| `knowledge/design/fast-path-services.json`    | always — it is pass 1 for every resource                |
| `references/design-refs/fast-path.md`         | always — the contract for what the table's labels claim  |
| `references/design-refs/specialist-gates.md`  | when any resource matches a `specialist_gates` row       |
| `references/design-refs/index.md`             | when any resource matched no row in the table            |
| the category file `index.md` names             | per category actually present — never speculatively      |

## The admission test for Direct Mappings

Stated once, in `fast-path.md` § The admission test. The short form: **is this target
correct regardless of the surrounding architecture?** Architecture-invariant rows are
admissible; everything else is a rubric decision. That is why the table is all
infrastructure primitives with one exception (`managedClusters` → EKS), and why Azure
Functions (`Microsoft.Web/sites` with `kind=functionapp`) → Lambda is a *rubric* row —
a function inside an otherwise Fargate-based workload may belong on Fargate, and a
durable or long-running function hits the eliminator anyway.

## Unknown types: two different unknowns

There are **two** distinct "we have no row for this", they arrive at different phases,
and conflating them is how a cost-bearing resource gets silently dropped.

### 1. Untranslated type (a Discover-level unknown) → always STOP

The Terraform type was absent from `arm-type-canonicalization.md`, so Discover recorded
it in `iac_metadata.untranslated_types` and left it **out of `resources[]` entirely**.
Read that list as a separate input — a resource that is not in `resources[]` cannot be
found by iterating `resources[]`, which is exactly how this case gets missed.

**A non-empty `untranslated_types` STOPs the design, unconditionally.**

The reason it is not run through the cost-bearing test: that test needs a SKU field, a
consumption row, or a provider namespace, and an untranslated resource has **none of the
three** — there is no canonical type, so there is no namespace, and Discover kept no
config. The skill cannot demonstrate the resource is free. Absence of evidence of cost
is not evidence of no cost, and the failure is asymmetric: wrongly stopping costs one
round trip to add a table row, while wrongly skipping understates the estate and the
estimate with nothing to signal it.

### 2. Unmapped canonical type (a Design-level unknown) → split

The type IS canonical and present in `resources[]`, but matched no row in
`fast-path-services.json` and has no row in `index.md`. Halting on every one of these
would stop Azure Design at roughly the third resource of a real inventory — tenants are
dense with diagnostic settings, private endpoints, role assignments, action groups, and
deployment records. So:

- **Benign** — no SKU/tier/capacity property in `config`, **and** no non-zero cost in
  consumption data → record in `warnings[]` and continue.
- **Cost-bearing** — has a SKU/tier/capacity property, **or** appears in RDfA/billing
  consumption with non-zero cost, **or** sits in a compute, data, network, or analytics
  provider namespace → **STOP** and ask for the type to be filed.

The consumption test is mechanical whenever RDfA or billing ran, so a resource that
costs money is never silently skipped. The namespace test is the fallback for an
IaC-only run, where there is no consumption data to consult.

### What a STOP writes

A STOP is not a crash. **Write `aws-design.json` with everything determined so far**,
plus a `halt` object, and then let the phase emit `GATE_FAIL`:

```jsonc
"halt": {
  "reason": "unknown_type",
  "blocking": [
    {
      "kind": "untranslated_terraform_type",   // or "unmapped_canonical_type"
      "identifier": "azurerm_dev_test_lab (local name: sandbox)",
      "action": "add a row to references/shared/arm-type-canonicalization.md, then re-run Design"
    }
  ]
}
```

Discarding the work would make the user re-run everything to learn one missing row, and
it would hide *which* resources were already fine. Writing the partial artifact is also
what makes the STOP testable by an external asserter. This is **not** the same as
patching an artifact to force a gate to pass — the gate still fails, loudly, and the
`halt` object is the reason.

## Missing rubric file → `pending_rubric[]`, not a guess

`index.md` names a category file per type. **If that file is not on disk, HALT** — same
guard, same reasoning, as `discover-iac.md` Step 2. Record each affected resource in
`pending_rubric[]` with its `azure_type`, the `ref_file` that is missing, and the
candidate targets `index.md` listed, then emit `GATE_FAIL`.

Do **not** map it from your own knowledge of Azure and AWS. "No rubric is needed" and
"the rubric has not been written yet" are otherwise indistinguishable, and improvising
past the second produces a mapping that satisfies every shape assertion, carries a
`confidence` label it did not earn, and differs between two runs of the same estate.

`pending_rubric[]` is a **build-phase section** that disappears once step 5 lands. It is
not part of the finished contract, which is why `design.md`'s `_postconditions` do not
mention it and do not pass while it is populated.

## Warning codes

Design writes its own `warnings[]` on `aws-design.json`, with the same entry shape as
Discover's (`schema-discover-azure.md` § Warnings: `code`, `azure_id` or `identifier`,
`detail`) and a **separate closed vocabulary**. Discover's codes describe what could not
be read; these describe what was decided.

| `code`                        | Emitted when                                                                        |
| ----------------------------- | ----------------------------------------------------------------------------------- |
| `skipped_no_aws_equivalent`   | a `skip_mappings` row with `kind: noise`                                             |
| `skipped_config_source`       | a `skip_mappings` row with `kind: config_source` — the `detail` MUST name what it contributed |
| `skipped_observability`       | an `Microsoft.Insights/*` or Log Analytics resource; carries `report_note: "cloudwatch_fallback"` |
| `app_consumed_by_plan`        | one per `Microsoft.Web/sites` folded into its plan, with `plan_azure_id`             |
| `idle_app_service_plan`       | a plan with zero apps; `severity: "cost_optimization"`                               |
| `benign_unknown_type`         | an unmapped canonical type that cleared the cost-bearing test                        |
| `<hard_blocker key>`          | a `hard_blockers` row, e.g. `azure_edition_windows_server`; `severity: "blocker"`     |

A cost-bearing unknown and an untranslated type produce a `halt` entry, **not** a
warning. That distinction is the whole point of the split policy: a warning means the
design continued, and these two mean it did not.

## Private endpoints are config sources, not targets

Skipped as standalone output, but their `privateLinkServiceId` /
`private_connection_resource_id` is read to build the app-to-data edge. Each consumed
endpoint gets one `warnings[]` entry naming the edge it produced. Every
`skip_mappings` row whose `kind` is `config_source` behaves this way: read the
contribution first, then skip, and name the contribution in the warning.

## The App Service Plan cost trap

`Microsoft.Web/serverfarms` carries the SKU and instance count — that is the compute
being paid for. `Microsoft.Web/sites` apps run on the plan and **share its capacity**.
Five web apps on one S1 plan cost one S1. Mapping each app to its own Elastic Beanstalk
environment multiplies the estimate by five.

This is the inverse of gcp's App Engine fan-out: GCP fans one parent out to N service
environments; Azure fans N apps **in** to one compute target.

1. Map the **plan** to the compute target, sized from the plan's SKU and instance
   count — never from the app count.
2. Apps become deployments onto that target. Each contributes runtime and app settings
   to `aws_config`; none emits its own compute line item.
3. Emit one mapping per plan, keyed by the plan's ARM ID, with one `warnings[]` entry
   per app consumed.
4. Split only on a stated isolation requirement from `preferences.json`, never by
   default — and when splitting, say plainly in the rationale that compute cost rises.
5. A plan with **zero** apps is idle capacity: map it, and flag it as a
   cost-optimization finding.

**Find the apps by the `hosted_on` edge**, which Discover writes from each site's
`service_plan_id` / `serverFarmId`. Do not group by resource group or by name prefix:
the edge is the only reliable link, and it is present for every discovery source.

The fan-in rule is **structural and independent of the target**, so it holds even while
the compute rubric is still pending: the count of compute units is one per plan whether
that plan resolves to Elastic Beanstalk, Fargate, or EKS. A plan sitting in
`pending_rubric[]` still accounts for its apps.

## Status — build step 3

Pass 1 is implemented: the disposition table, its contract, the routing index, the gate
table, the split unknown-type policy, and the fan-in rule. Pass 2 lands in step 5, and
until it does this fragment halts on any estate carrying compute or a relational
database rather than improvising a target.

Exercised by the `azure-iac-terraform` fixture's Design asserter
(`check_expected_design.py`), which pins the fan-in count, the untranslated-type STOP,
and the three protocol/API-conditioned rows.
