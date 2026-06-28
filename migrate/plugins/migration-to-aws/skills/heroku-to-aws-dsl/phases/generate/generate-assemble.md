---
_assemble: generate-assemble
_of_phase: generate
_scope: >
  Validate the complete generated artifact set across both fragments
  (terraform + docs/scripts). ONLY this. Creates nothing, mutates nothing. Does
  NOT update .phase-status.json.
_reads: [terraform/, MIGRATION_GUIDE.md, README.md, scripts/, generation-warnings.json, aws-design.json]
_mutates: []
_produces: []
_postconditions:
  - _check_file_exists: [terraform/main.tf, terraform/variables.tf, terraform/outputs.tf, MIGRATION_GUIDE.md, README.md]
  - _assert: "at least one domain .tf file (compute/database/cache/messaging) or vpc.tf exists beyond the core files"
  - _assert: "terraform/variables.tf declares at least aws_region"
  - _assert: "MIGRATION_GUIDE.md has Prerequisites and Verification sections"
  - _assert: "CROSS-ARTIFACT: every service in aws-design.json.services[] is either generated in a terraform .tf OR listed in generation-warnings.json.warnings[]"
  - _assert: "CROSS-ARTIFACT: every file README.md references in its artifact table actually exists in $MIGRATION_DIR/"
  - _assert: "NO {{...}} placeholder remains in any terraform .tf file (those become var.* or resolved values)"
  - _assert: "REFERENCE INTEGRITY: every aws_security_group.<name> referenced in any .tf (compute references fargate/alb; database references database; cache references cache; messaging references messaging) resolves to a security group DECLARED in security.tf. (The restricted + standard security templates both define the tiered SGs; a domain file referencing an undeclared SG is a fail-closed GATE_FAIL.)"
  - _assert: "if Postgres in design -> scripts/migrate-postgres.sh exists; if Redis -> scripts/migrate-redis.sh exists"
  - _assert: "generation-warnings.json validates against schemas/generation-warnings.schema.json"
  - _assert: "if any service has aws_service == 'EKS' or design has eks_cluster -> terraform/eks.tf + kubernetes/ exist (else N/A — EKS not authored)"
_on_error:
  _unrecoverable: { effect: "stop; surface error", status: revert_to_pending }
---

# Generate Assembler

## Orientation

The mandatory generate-phase ASSEMBLER (exactly one per phase, terminal), here a
CROSS-ARTIFACT validator — the taxonomy's first non-trivial multi-artifact
assembler. The two fragments wrote independent artifact sets (terraform/ +
warnings; docs + scripts); this unit creates nothing and mutates nothing, but
owns the WHOLE-SET contract: required files present, every designed service
generated-or-warned, README references resolve to real files, no placeholder
leakage in `.tf`, conditional scripts present. Its `_postconditions` ARE the
generate handoff gate. It reads the generated artifacts + `aws-design.json` (the
input — to cross-check coverage). Does NOT update `.phase-status.json`.

## Step: validate_artifact_set

```meta
_reads: [terraform/, MIGRATION_GUIDE.md, README.md, scripts/, generation-warnings.json, aws-design.json]
```

Run every check in this unit's `_postconditions`. The CROSS-ARTIFACT checks span
the two fragments' outputs: re-read `aws-design.json.services[]` and confirm each
appears either as a generated terraform resource or in
`generation-warnings.json.warnings[]` (a service neither generated nor warned is
a fail-closed GATE_FAIL — coverage hole). Re-read `README.md`'s artifact table and
confirm every referenced file exists on disk. Grep every `terraform/*.tf` for a
residual `{{` placeholder.

Fail-closed (Golden Rule 1): on any failure emit
`GATE_FAIL | phase=generate | field=<path> | reason=missing|invalid`, do NOT
edit artifacts to force a pass, do NOT advance, and tell the user what failed.
Do NOT re-design or re-estimate — this validator only checks the generated set.
