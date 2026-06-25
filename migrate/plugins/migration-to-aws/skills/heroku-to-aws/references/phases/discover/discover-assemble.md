# Discover Phase: Assemble Inventory

> Reads intermediate discovery outputs and assembles the final `heroku-resource-inventory.json`.
> Always runs as the last discover route.

---

## Step 1: Read Intermediate Files

Read from `$MIGRATION_DIR`:

- `_terraform-discovery.json` (if exists) — resources extracted from Terraform + Procfile/app.json
- `_billing-discovery.json` (if exists) — billing profile from Heroku invoices/exports

If neither file exists, STOP: "No discovery data available. Ensure Terraform files with heroku_* resources exist in the project."

---

## Step 2: Assemble Inventory

Load `references/shared/schema-discover-heroku.md` for the complete schema.

Merge inputs into `heroku-resource-inventory.json`:

1. **Resources array**: Take all entries from `_terraform-discovery.json` → `resources[]`. This is a flat array (no clustering, no dependency graphs).

2. **Apps array**: Build from `_terraform-discovery.json` → `apps[]` (per-app entries with `app_name`, `heroku_generation`, `space`, parse warnings).

3. **Metadata**: Assemble from available sources:
   - `discovery_timestamp`: current ISO 8601
   - `total_apps_discovered`: count of unique apps
   - `discovery_sources`: `["terraform"]` + `["procfile"]` if Procfile was found + `["billing"]` if billing exists
   - `confidence`: `"full"` if no parse warnings, `"reduced"` otherwise

4. **Terraform metadata**: Include from `_terraform-discovery.json` → `terraform_metadata` section.

5. **Billing profile**: If `_billing-discovery.json` exists, include as `billing_profile` section with `available: true`, `total_monthly_cost`, `currency`, `billing_period`, `line_items`.

6. **Validation**: Verify:
   - Every resource has `resource_id`, `resource_type`, `heroku_app`, `config`
   - No forbidden fields: `cluster_id`, `creation_order_depth`, `edges`, `dependencies`, `must_migrate_together`

---

## Step 3: Write Output

Write `heroku-resource-inventory.json` to `$MIGRATION_DIR`.

Report to user:
- "Discovered X resources across Y apps."
- If billing: "Parsed billing data ($Z/month)."
- If Procfile found: "Supplemented with Procfile commands."

---

## Scope Boundary

**This phase covers Heroku Discovery ONLY.**

FORBIDDEN — Do NOT include ANY of:
- AWS service names, recommendations, or equivalents
- Migration strategies or timelines
- Cost estimates or comparisons
