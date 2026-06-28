---
_assemble: estimate-assemble
_of_phase: estimate
_scope: >
  Validate the cost-engine's estimation-infra.json against the schema and the
  estimate handoff gate (Property-16 total invariant, every-service-priced,
  recommendation/complexity gates). ONLY this. Creates nothing, mutates nothing.
  Does NOT update .phase-status.json.
_reads: [estimation-infra.json, aws-design.json]
_mutates: []
_produces: []
_postconditions:
  - _validate_json: estimation-infra.json
  - _validate_schema: { file: estimation-infra.json, schema: schemas/estimation-infra.schema.json }
  - _assert: "estimation-infra.json has phase == 'estimate' and a valid timestamp"
  - _assert: "projected_costs.aws_monthly_balanced is a positive number"
  - _assert: "PROPERTY-16: aws_monthly_balanced equals the arithmetic sum of breakdown[].mid (excluding lines with pricing_source == 'unpriced')"
  - _assert: "every service in aws-design.json.services[] appears in projected_costs.breakdown[] (by service_id or service) OR is listed unpriced in warnings"
  - _assert: "complexity_tier is one of small, medium, large"
  - _assert: "recommendation.path is migrate_optimized|migrate_phased|stay; path_label non-empty; migrate_if and stay_if are non-empty arrays"
  - _assert: "no design mapping, Terraform/HCL, or migration runbook content appears anywhere in the artifact (out of scope)"
_on_error:
  _unrecoverable: { effect: "stop; surface error", status: revert_to_pending }
---

# Estimate Assembler

## Orientation

The mandatory estimate-phase ASSEMBLER (exactly one per phase, terminal), here a
validator: the cost-engine fragment already created `estimation-infra.json` and
there is nothing to combine, so this unit creates nothing and mutates nothing —
it owns the artifact contract (schema validity, the Property-16 total ==
sum-of-lines invariant, every-design-service-priced, and the
recommendation/complexity gates), expressed as its `_postconditions`, which are
the estimate handoff gate. It reads `estimation-infra.json` (the artifact) and
`aws-design.json` (the phase input — to confirm every designed service is priced
or warned).

## Step: validate_estimate

```meta
_reads: [estimation-infra.json, aws-design.json]
```

Read `estimation-infra.json`. Run every check in this unit's `_postconditions`.
The **Property-16** check re-derives the sum of `breakdown[].mid` (excluding
`unpriced` lines) and confirms it equals `aws_monthly_balanced` — a missing or
mis-added line is a fail-closed GATE_FAIL, not a silent discrepancy. The
every-service-priced check re-reads `aws-design.json.services[]` and confirms
each appears in the breakdown (or is explicitly listed as `unpriced` in
warnings).

Fail-closed (Golden Rule 1): on any failure emit
`GATE_FAIL | phase=estimate | field=<path> | reason=missing|invalid`, do NOT
modify `estimation-infra.json` to force a pass, do NOT advance, and tell the user
what failed. Do NOT introduce design/Terraform/runbook content — this validator
only checks the financial artifact.
