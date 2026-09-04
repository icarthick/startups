---
_assemble: assemble-estimation
_of_phase: estimate
_reads:
  - infra (fragment contribution)
_produces:
  - estimation-infra.json
_knowledge:
  - { file: references/vendored/estimate/estimation-infra.schema.json }
  - { file: references/vendored/workshop/workshop-invariants.md }
---

# Estimate — Assemble Estimation and Present the Decision Gate

> **Assembler unit.** The single creator of `estimation-infra.json`. It also owns the
> post-Estimate decision gate and is the only unit that writes `run_mode`. See
> `estimate.md` for how it is composed into the phase.

## Assembly rules

1. Merge the cost-engine contribution into `estimation-infra.json` per
   `references/vendored/estimate/estimation-infra.schema.json`.
2. Verify the right-sized total is the arithmetic sum of its per-service costs,
   excluding unpriced entries. A total that does not reconcile is a gate failure, not
   a rounding note.
3. Classify `complexity_tier` per `references/vendored/estimate/complexity-tiers.json`.

## The decision gate

Generate is opt-in. Present three options:

```
[A] That's what I needed for now — stop here with the design and the estimate
[B] Explore what-if scenarios (change region, HA, compute target, architecture) before deciding
[C] Generate the migration artifacts — Terraform, migration scripts, and docs
```

- **A** → write `run_mode: "decide"`. The run is complete and useful; do not nag.
- **B** → write `run_mode: "decide"`, keep `current_phase: estimate`, and enter the
  `workshop` sidebar. The gate is re-presented when the sidebar resolves.
- **C** → write `run_mode: "decide_and_execute"` **before** `generate.md` loads, so a
  session that dies mid-Generate resumes as an Execute run instead of re-asking a
  question the user already answered.

`run_mode` is a top-level key in `.phase-status.json`, defined in the vendored
`state/phase-status.schema.json`. An absent `run_mode` is not consent.

## Status — skeleton (build step 1)

Writes the artifact and owns the gate contract above. The gate presentation and the
dual-output rendering land in step 6.
