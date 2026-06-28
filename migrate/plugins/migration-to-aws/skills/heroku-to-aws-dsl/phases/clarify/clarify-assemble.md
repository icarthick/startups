---
_assemble: clarify-assemble
_of_phase: clarify
_scope: >
  Validate the interview fragment's preferences.json against the schema and the
  conditional validation checklist. ONLY this — no AWS configs, no cost, no
  sizing. Creates nothing, mutates nothing (pure validator). Does NOT update
  .phase-status.json.
_reads: [preferences.json, heroku-resource-inventory.json]
_mutates: []
_produces: []
_postconditions:
  - _validate_json: preferences.json
  - _validate_schema: { file: preferences.json, schema: schemas/preferences.schema.json }
  - _assert: "global.target_region is a valid AWS region code"
  - _assert: "global.availability is populated"
  - _assert: "if inventory has a heroku-postgresql addon -> data.database_ha is set (non-null)"
  - _assert: "if inventory has a heroku-postgresql addon -> global.migration_approach is set (non-null)"
  - _assert: "if inventory has a heroku-postgresql addon -> data.migration_method is set (non-null)"
  - _assert: "if global.migration_approach == 'interim_cutover_data_first' -> global.target_exit_date is non-null and a valid future ISO date AND global.interim_cutover == true"
  - _assert: "if any app has heroku_generation == 'fir' -> global.fir_intent is set (non-null)"
  - _assert: "if a Private Space with peering is detected AND subnet IDs were required -> network.subnet_ids is a non-empty array of 1-6 valid subnet IDs"
  - _assert: "operational.containerization_status is populated"
  - _assert: "design_constraints.kubernetes.value is one of eks-managed, eks-or-ecs, ecs-fargate AND chosen_by is user or default"
  - _assert: "every entry in sources has value 'user' or 'default'"
  - _assert: "metadata.clarify_mode is 'fast_path' or 'full'"
  - _assert: "only keys with non-null values are present (no explicit-null sections)"
  - _assert: "preferences-draft.json no longer exists in $MIGRATION_DIR/"
_on_error:
  _unrecoverable: { effect: "stop; surface error", status: revert_to_pending }
---

# Clarify Assembler

## Orientation

The mandatory clarify-phase ASSEMBLER (exactly one per phase, terminal), here a
NO-OP / PROMOTE validator: the interview fragment already CREATED
`preferences.json` and there is nothing to combine (single-fragment phase), so
this unit creates nothing and mutates nothing — it owns the ARTIFACT-LEVEL
CONTRACT (schema validity plus the conditional validation checklist whose checks
depend on what the inventory contained), expressed as its `_postconditions`,
which are the phase's fail-closed handoff gate. It reads two files from
`$MIGRATION_DIR/`: `preferences.json` (the artifact to validate) and
`heroku-resource-inventory.json` (needed for the conditional checks — e.g. "if
Postgres present then database_ha required").

## Step: validate_preferences

```meta
_reads: [preferences.json, heroku-resource-inventory.json]
```

Read `preferences.json`. Run every check in this unit's `_postconditions`. The
inventory-dependent checks (Postgres → database_ha / migration_approach /
migration_method; Fir → fir_intent; peering → subnet_ids) are evaluated by
re-reading `heroku-resource-inventory.json` to determine whether each trigger
condition held — a value is required ONLY when its triggering resource is
present.

This is fail-closed (Golden Rule 1): if any check fails, emit
`GATE_FAIL | phase=clarify | field=<path> | reason=missing|invalid`, do NOT
modify `preferences.json` to force a pass, do NOT advance, and tell the user
which question to (re)answer.

Do NOT introduce any AWS service names, cost numbers, sizing, or Terraform —
this validator only checks the requirements artifact.
