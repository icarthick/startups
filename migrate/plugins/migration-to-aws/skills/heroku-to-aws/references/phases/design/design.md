# Phase 3: Design AWS Architecture

> Maps each Heroku resource to its AWS equivalent using deterministic lookup tables.
> Produces `aws-design.json` in `$MIGRATION_DIR`.

---

## Step 1: Generate Design

Call the `heroku_design` MCP tool:

```
heroku_design(migration_dir=$MIGRATION_DIR)
```

This tool reads `heroku-resource-inventory.json` and `preferences.json`, then:
- Maps formations → Fargate (dyno type table) + ALB for web processes
- Maps heroku-postgresql → RDS/Aurora (postgres plan table + availability preference)
- Maps heroku-redis → ElastiCache (redis plan table)
- Maps heroku-kafka → Amazon MSK (kafka plan table)
- Maps other add-ons → AWS via fast-path table (13 known mappings)
- Defers unrecognized add-ons to specialist gate
- Generates VPC design (new or existing based on Private Space peering)
- Detects Fir-generation workloads (detect-only warning)
- Writes `aws-design.json` to `$MIGRATION_DIR`

---

## Step 2: Report to User

From the tool's summary, report:

- "Designed X AWS services across Y apps."
- If deferred: "Deferred N add-on(s) to specialist engagement: [names]."
- If Fir detected: "Fir-generation workloads noted as deferred (detect-only)."
- If warnings: surface pipeline/dyno warnings.
- VPC mode: "VPC design: [new VPC generated | existing VPC referenced]."

---

## Scope Boundary

**This phase covers AWS architecture design ONLY.**

FORBIDDEN — Do NOT include ANY of:
- Cost estimates or pricing
- Terraform code generation
- Migration timelines or execution plans
- Manual sizing decisions (all sizing is from lookup tables)
