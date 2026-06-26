# Discover Phase: Assemble Inventory

> Merges intermediate discovery outputs into the final `heroku-resource-inventory.json`.
> Always runs as the last discover route.

---

## Step 1: Assemble

Call the `assemble_heroku_inventory` MCP tool:

```
assemble_heroku_inventory(migration_dir=$MIGRATION_DIR)
```

This tool:
- Reads `_terraform-discovery.json` and `_billing-discovery.json` from `$MIGRATION_DIR`
- Merges resources, apps, metadata, terraform_metadata, and billing_profile
- Validates required fields and checks for forbidden clustering fields
- Writes `heroku-resource-inventory.json`

If the tool returns `status: "error"`, no discovery data exists — report to user.

If `validation_errors` is non-empty, review and fix the flagged resources.

Report: "Discovered X resources across Y apps. Sources: [terraform, procfile, billing]."
