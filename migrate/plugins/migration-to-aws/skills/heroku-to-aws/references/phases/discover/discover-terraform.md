# Discover Phase: Terraform Discovery (Primary Path)

> Scans `.tf` files for `heroku_*` resources, extracts configuration, integrates Procfile/app.json,
> and writes `_terraform-discovery.json` to `$MIGRATION_DIR`.

---

## Step 1: Scan Heroku Terraform

Call the `heroku_discover_terraform` MCP tool:

```
heroku_discover_terraform(project_dir=<project root>, migration_dir=$MIGRATION_DIR)
```

This tool:
- Finds all `.tf` files and extracts `heroku_*` resource blocks
- Resolves cross-references (e.g., `heroku_app.web.id` → app name)
- Parses Procfile (supplements formations with commands)
- Parses app.json (supplements with buildpacks, declared add-ons)
- Detects Cedar/Fir generation from `stack` attribute
- Writes `_terraform-discovery.json` to `$MIGRATION_DIR`

If the tool returns `status: "skipped"`, no Heroku Terraform resources were found — exit cleanly.

Report to user: "Scanned X resources across Y apps. Sources: [terraform, procfile, ...]"

---

## Step 2: Review and Resolve Gaps

Check the tool's return for:

- **`unresolved_references`** — resources where `heroku_app` couldn't be determined. Read the flagged `.tf` files, resolve the variable/reference, and update the entry in `_terraform-discovery.json`.

- **`parse_warnings`** — blocks the tool couldn't parse. Read the raw HCL for those blocks and manually extract the resource attributes into the expected inventory format.

If no gaps (`unresolved_references` is empty and `parse_warnings` is 0), no action needed — proceed.

---

## Scope Boundary

**This phase covers Heroku Discovery ONLY.**

FORBIDDEN — Do NOT include ANY of:
- AWS service names, recommendations, or equivalents
- Migration strategies or timelines
- Cost estimates or comparisons
