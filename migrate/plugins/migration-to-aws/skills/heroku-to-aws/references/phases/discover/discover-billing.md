# Discover Phase: Billing Discovery

> Parses Heroku billing exports (Enterprise CSV, Dashboard invoices) and writes
> `_billing-discovery.json` to `$MIGRATION_DIR`.

---

## Step 1: Extract Heroku Billing

Call the `heroku_discover_billing` MCP tool:

```
heroku_discover_billing(project_dir=<project root>, migration_dir=$MIGRATION_DIR)
```

This tool:
- Finds billing files (`*billing*.csv`, `*invoice*.csv`, `*billing*.json`, `*invoice*.json`)
- Auto-detects format (Enterprise CSV, Dashboard invoice, API JSON)
- Parses per-app cost breakdown (dyno, addon, platform categories)
- Writes `_billing-discovery.json` to `$MIGRATION_DIR`

If the tool returns `status: "skipped"`, no billing files were found — exit cleanly.

Report to user: "Parsed billing data: $X/month across Y line items (format: [source_format])."

---

## Scope Boundary

**This sub-file covers billing data parsing ONLY.**

FORBIDDEN — Do NOT include ANY of:
- AWS service names, recommendations, or equivalents
- Cost estimates or projections for AWS
- Cost comparisons between Heroku and AWS
