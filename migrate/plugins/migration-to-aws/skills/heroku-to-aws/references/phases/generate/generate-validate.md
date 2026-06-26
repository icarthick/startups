# Generate Phase: Validate Completeness

> Runs after terraform and docs generation. Verifies every designed service
> is accounted for in generated artifacts.

---

## Step 1: Cross-Reference Check

Read `$MIGRATION_DIR/aws-design.json` → `services[]`.

For each service entry, verify ONE of:

- The service is referenced in a file under `$MIGRATION_DIR/terraform/` (search for `service_id` or the AWS resource type)
- The service is listed in `$MIGRATION_DIR/generation-warnings.json`

**If any service is missing from both:** Report to user:

> "Warning: [service_id] ([aws_service]) is in the design but not generated in Terraform and not listed in generation-warnings.json. This service will need manual setup."

Add it to `generation-warnings.json` (create the file if it doesn't exist).

---

## Step 2: Verify Core Files

Confirm these files exist in `$MIGRATION_DIR/`:

- `terraform/main.tf`
- `terraform/variables.tf`
- `MIGRATION_GUIDE.md`
- `README.md`

If any are missing, report which file is absent and stop.

---

## Step 3: Summary

Report artifact count:

- "Generate phase complete: [N] Terraform files, MIGRATION_GUIDE.md, README.md, [M] migration scripts."
- If warnings: "[W] service(s) deferred — see generation-warnings.json."
