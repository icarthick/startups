---
_assemble: design-assemble
_of_phase: design
_scope: >
  Validate the mapping fragment's aws-design.json against the schema-shape rules
  and the route output gates (conditional on what the inventory contained). ONLY
  this. Creates nothing, mutates nothing (pure validator). Does NOT update
  .phase-status.json.
_reads: [aws-design.json, heroku-resource-inventory.json]
_mutates: []
_produces: []
_postconditions:
  - _validate_json: aws-design.json
  - _validate_schema: { file: aws-design.json, schema: schemas/aws-design.schema.json }
  - _assert: "aws-design.json has phase=='design' and a valid timestamp"
  - _assert: "services[] present (empty only if ALL resources deferred to specialist gate)"
  - _assert: "every services[] entry has service_id, source_resource_id, heroku_app, aws_service, confidence, aws_config"
  - _assert: "every deferred[] entry has addon_name, addon_plan, provider, reason, recommendation"
  - _assert: "vpc_design present with mode in {existing_vpc, new_vpc}"
  - _assert: "if vpc_design.mode == existing_vpc -> existing_vpc_id non-empty"
  - _assert: "if vpc_design.mode == new_vpc -> >=2 subnets across separate AZs"
  - _assert: "metadata.total_services == services[].length"
  - _assert: "no ARM/Graviton/CNB targeting anywhere in output (Fir detect-only)"
  - _assert: "ROUTE GATE: if inventory had formations -> services[] has >=1 Fargate (or EKS) entry, unless ALL dyno types were unrecognized"
  - _assert: "ROUTE GATE: if inventory had recognized heroku-postgresql -> services[] has an RDS or Aurora entry"
  - _assert: "ROUTE GATE: if inventory had recognized heroku-redis -> services[] has an ElastiCache entry"
  - _assert: "ROUTE GATE: if inventory had recognized heroku-kafka -> services[] has an MSK entry"
  - _assert: "ROUTE GATE: if inventory had pipelines -> warnings[] has a pipeline detect-only warning"
_on_error:
  _unrecoverable: { effect: "stop; surface error", status: revert_to_pending }
---

# Design Assembler

## Orientation

The mandatory design-phase ASSEMBLER (exactly one per phase, terminal), here a
validator/promote: the mapping fragment already created `aws-design.json` and
there is nothing to combine (single-fragment phase), so this unit creates
nothing and mutates nothing — it owns the artifact-level contract (schema-shape
validity, per-entry required fields, the VPC contract, and the ROUTE OUTPUT
GATES), expressed as its `_postconditions`, which are the design handoff gate.

It reads `aws-design.json` (the artifact) and `heroku-resource-inventory.json`
(the phase input — needed to evaluate the route gates, e.g. "if the inventory had
a recognized postgres addon, the design must contain an RDS/Aurora entry"); per
the interpreter, a validator assembler may read the phase input for
trigger-dependent contracts.

## Step: validate_design

```meta
_reads: [aws-design.json, heroku-resource-inventory.json]
```

Read `aws-design.json`. Run every check in this unit's `_postconditions`. The
ROUTE GATE checks re-read `heroku-resource-inventory.json` to know what the
design was OBLIGATED to produce: each recognized core resource type present in
the inventory must have its corresponding service entry in the design (a missing
mapping is a fail-closed GATE_FAIL, not a silent omission). "Recognized" means
the plan/dyno type matched its table; a deferred (unrecognized) resource is
exempt — it legitimately produced a `deferred[]` entry instead.

Fail-closed (Golden Rule 1): on any failure emit
`GATE_FAIL | phase=design | field=<path> | reason=missing|invalid`, do NOT
modify `aws-design.json` to force a pass, do NOT advance, and tell the user what
failed and how to fix it.

Do NOT introduce cost, Terraform, or scripts — this validator only checks the
design artifact.
