---
_assemble: discover-assemble
_of_phase: discover
_scope: >
  Combine the discover fragments' outputs into the final
  `heroku-resource-inventory.json` and own its artifact-level contract. ONLY
  this — no AWS names, no cost, no clustering. Does NOT update
  `.phase-status.json`.
_reads: [heroku-resource-inventory.json, billing-profile.json]
_mutates: [heroku-resource-inventory.json]
_produces: []
_postconditions:
  - _validate_json: heroku-resource-inventory.json
  - _validate_schema: { file: heroku-resource-inventory.json, schema: schemas/heroku-resource-inventory.schema.json }
  - _assert: "NO resource or top-level field is one of: cluster_id, creation_order_depth, edges, dependencies, must_migrate_together"
  - _assert: "if billing-profile.json existed -> inventory.billing_profile.available is present"
  - _assert: "metadata.discovery_sources includes every fragment that ran"
_on_error:
  _unrecoverable: { effect: "stop; surface error", status: revert_to_pending }
---

# Discover Assembler

> The mandatory discover-phase ASSEMBLER (exactly one per phase, terminal). The
> terraform fragment CREATED `heroku-resource-inventory.json`; this assembler
> MUTATES it in place to fold in billing (if present) and owns the final
> artifact-level contract. It is the file's last writer, so it owns the file's
> final postconditions (schema, forbidden-fields).
>
> Reads files from `$MIGRATION_DIR/` (no in-memory cross-fragment hand-off):
> the terraform-created inventory, and `billing-profile.json` IF the billing
> fragment ran. Does NOT update `.phase-status.json`.

## Step: fold_in_billing

```meta
_mutates: heroku-resource-inventory.json
```

Read `heroku-resource-inventory.json` (created by the terraform fragment).

- If `billing-profile.json` exists (billing fragment ran): read it and set the
  inventory's `billing_profile` to its contents; add `"billing"` to
  `metadata.discovery_sources`.
- If it does NOT exist (billing skipped or all files failed): set
  `billing_profile = {available:false}`.

Set `metadata.confidence` to `"full"` if every fragment that ran parsed clean
(no `parse_warnings`), else `"reduced"`. Do not otherwise reshape the
terraform-written sections.

MUST NOT introduce forbidden clustering fields anywhere: `cluster_id`,
`creation_order_depth`, `edges`, `dependencies`, `must_migrate_together`.

## Output

This assembler MUTATES `heroku-resource-inventory.json` (the phase's artifact) to
its final form and validates it via this unit's `_postconditions`. It creates no
new files (`_produces: []`). After it passes, the phase `_postconditions` run;
on full pass the interpreter emits `HANDOFF_OK | phase=discover | ...` and
advances to clarify.

## Scope

Fold the fragments' outputs into one flat inventory and validate it. Nothing
else — no AWS names, no cost, no clustering.
