---
_assemble: design-assemble
_of_phase: design
_scope: >
  Merge the EKS fragment's _eks-design.json into aws-design.json (when present),
  then validate the merged design against the schema-shape rules and the route
  output gates. ONLY this. Does NOT update .phase-status.json.
_reads: [aws-design.json, _eks-design.json, heroku-resource-inventory.json]
_mutates: [aws-design.json]
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
  - _assert: "ROUTE GATE: if inventory had formations -> services[] has >=1 Fargate (Fargate path) OR EKS (eks path) entry, unless ALL dyno types were unrecognized"
  - _assert: "if any EKS service exists -> aws-design.json has an eks_cluster (merged from _eks-design.json) and NO Fargate formation entries (all-or-nothing)"
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
MERGER + validator (the discover-style shape): the mapping-engine fragment
created `aws-design.json` (non-formation + VPC + Fir + Fargate formations), and
WHEN the EKS path fired the eks-mapping fragment created `_eks-design.json` (EKS
services + the `eks_cluster`). This assembler MERGES the latter into the former
(appends `eks_services[]` into `services[]`, adds the `eks_cluster` key) and owns
the artifact-level contract (schema-shape, per-entry fields, VPC, ROUTE OUTPUT
GATES). One creator per artifact; the assembler is the only mutator.

It reads `aws-design.json`, `_eks-design.json` (if the EKS fragment ran), and
`heroku-resource-inventory.json` (the phase input — to evaluate the route gates).

## Step: merge_eks

```meta
_reads: [aws-design.json, _eks-design.json]
_mutates: aws-design.json
```

IF `_eks-design.json` exists (the EKS path fired): read it and fold it into
`aws-design.json` — append every `eks_services[]` entry into `services[]`, set the
top-level `eks_cluster` key to its `eks_cluster`. Recompute
`metadata.total_services` = final `services[].length`. (The mapping-engine left
no Fargate formation entries in EKS mode, so there is no Fargate/EKS mix.) IF
`_eks-design.json` does NOT exist (Fargate / no formations), this step is a no-op.

## Step: validate_design

```meta
_reads: [aws-design.json, heroku-resource-inventory.json]
```

Read the (now merged) `aws-design.json`. Run every check in this unit's `_postconditions`. The
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
