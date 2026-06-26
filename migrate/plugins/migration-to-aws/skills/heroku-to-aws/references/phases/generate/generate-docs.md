# Generate Phase: Documentation and Scripts

> Produces MIGRATION_GUIDE.md, README.md, and database migration scripts.

---

## Step 1: Generate Documentation

Call the `heroku_generate_docs` MCP tool:

```
heroku_generate_docs(migration_dir=$MIGRATION_DIR)
```

This tool reads `aws-design.json`, `preferences.json`, and `heroku-resource-inventory.json`, then:
- Generates `MIGRATION_GUIDE.md` with conditional sections based on services in design
- Generates `README.md` listing all artifacts
- Generates `scripts/migrate-postgres.sh` (if PostgreSQL in design)
- Generates `scripts/migrate-redis.sh` (if Redis in design)
- Sets executable permissions on scripts

---

## Step 2: Review Output

Check generated files for:
- `{{PLACEHOLDER}}` values that need user input (intentional — user fills these)
- Conditional sections correctly included/omitted based on design
- Scripts are executable (`chmod +x`)

---

## Scope Boundary

FORBIDDEN — Do NOT:
- Modify the design or estimate
- Add services not in `aws-design.json`
- Fill in user placeholders (those are for the user)
