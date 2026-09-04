---
_fragment: infra
_of_phase: design
_contributes:
  - aws-design.json (services[], clusters[], deferred[], warnings[])
---

# Design — Infrastructure Mapping

> **Fragment unit.** See `design.md` for how it is composed into the phase.

Runs the two-pass mapping engine over the clustered inventory: pass 1 is the
deterministic fast-path table, pass 2 is the category rubric. It applies the
precedence order in `design.md` and never reorders it.

## The admission test for Direct Mappings

The invariant in `design.md` yields a sharper test than "is it 1:1?": **is this
target correct regardless of the surrounding architecture?** Architecture-invariant
rows are admissible; everything else is a rubric decision. That is why the table is
all infrastructure primitives and contains no compute — and why Azure Functions
(`Microsoft.Web/sites` with `kind=functionapp`) → Lambda is a *rubric* row, not a
fast-path one: a function inside an otherwise Fargate-based workload may belong on
Fargate, and a durable or long-running function hits the eliminator anyway.

## Unknown types: warn-and-skip or STOP

Halting the whole design on any unrecognized type would stop Azure Design at roughly
the third resource of a real inventory — tenants are dense with diagnostic settings,
private endpoints, role assignments, action groups, and deployment records. So the
policy splits:

- **Benign unknown** — no SKU/tier/capacity property, and no non-zero cost in
  consumption data → record in `warnings[]` and continue.
- **Cost-bearing unknown** — has a SKU/tier/capacity property, **or** appears in
  RDfA/billing consumption with non-zero cost, **or** sits in a compute, data,
  network, or analytics provider namespace → **STOP** and ask for the type to be
  filed.

The consumption test is mechanical whenever RDfA or billing ran, so a resource that
costs money is never silently skipped.

**Private endpoints are edge-bearing config sources, not targets.** They are skipped
as standalone output, but their `privateLinkServiceId` is read to build the
app-to-data edge. Each consumed endpoint gets one `warnings[]` entry naming the edge
it produced.

## The App Service Plan cost trap

`Microsoft.Web/serverfarms` carries the SKU and instance count — that is the compute
being paid for. `Microsoft.Web/sites` apps run on the plan and **share its
capacity**. Five web apps on one S1 plan cost one S1. Mapping each app to its own
Elastic Beanstalk environment multiplies the estimate by five.

This is the inverse of gcp's App Engine fan-out: GCP fans one parent out to N service
environments; Azure fans N apps **in** to one compute target.

1. Map the **plan** to the compute target, sized from the plan's SKU and instance
   count — never from the app count.
2. Apps become deployments onto that target. Each contributes runtime and app
   settings to `aws_config`; none emits its own compute line item.
3. Emit one mapping per plan, keyed by the plan's ARM ID, with one `warnings[]` entry
   per app consumed.
4. Split only on a stated isolation requirement from `preferences.json`, never by
   default — and when splitting, say plainly in the rationale that compute cost rises.
5. A plan with **zero** apps is idle capacity: map it, and flag it as a
   cost-optimization finding.

## Status — skeleton (build step 1)

Wiring only. The tables and rubrics this fragment executes land in steps 3–5; the
rules above are the contract they will be written against.
