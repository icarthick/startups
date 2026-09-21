---
_assemble: generate
_of_phase: generate
_produces:
  - generation-warnings.json
---

# Generate Phase: Assembler

Cross-artifact validation, write `generation-warnings.json`, and update phase status.

---

## Step 1: Cross-Artifact Validation

1. Verify all files in `_produces` exist in `$MIGRATION_DIR/`.
2. Verify `terraform/main.tf` has at least one `resource` block.
3. Verify `terraform/variables.tf` declares an `aws_region` variable.
4. Verify no `{{VARIABLE}}` placeholder tokens remain in any `.tf` file.
5. Verify `MIGRATION_GUIDE.md` contains "Prerequisites" and "Verification" sections.
6. Verify `README.md` lists at least one artifact.
7. If Postgres is in `aws-design.json`: verify `scripts/migrate-postgres.sh` exists.
8. For every entry in `aws-design.json` services[]: verify it appears in generated files
   OR in the deferred list below.

---

## Step 2: Write generation-warnings.json

Collect any deferred or unpriced resources:

```json
{
  "deferred_services": [],
  "unpriced_services": [],
  "notes": []
}
```

Populate from `aws-design.json` deferred[] and `estimation-infra.json` warnings[].

---

## Step 3: Update .phase-status.json

Set `phases.generate` to `"completed"` and `current_phase` to `"complete"` in
`$MIGRATION_DIR/.phase-status.json`.

Emit: `HANDOFF_OK | phase=generate`

---

## Step 4: Present Completion Summary

Output to the user:

```
## Migration artifacts generated

**Location:** .migration/<run-id>/

| Artifact | Status |
| -------- | ------ |
| terraform/ | ✓ Generated |
| MIGRATION_GUIDE.md | ✓ Generated |
| README.md | ✓ Generated |
<if deferred:> | generation-warnings.json | ✓ N deferred services |

**Next steps:** Follow MIGRATION_GUIDE.md — review the Terraform plan, run the data
migration scripts, then cut over DNS.
```
