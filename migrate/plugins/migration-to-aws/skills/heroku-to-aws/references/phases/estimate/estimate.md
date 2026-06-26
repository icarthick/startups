# Phase 4: Estimate AWS Costs

> Calculates projected AWS monthly costs, compares with Heroku baseline,
> classifies complexity, and produces `estimation-infra.json`.

---

## Step 1: Generate Estimate

Call the `estimate_heroku_migration` MCP tool:

```
estimate_heroku_migration(migration_dir=$MIGRATION_DIR)
```

This tool reads `aws-design.json`, `preferences.json`, and `heroku-resource-inventory.json`, then:
- Calculates per-service monthly cost using cached AWS pricing
- Generates 3 tiers: Premium (1.3x), Balanced (baseline), Optimized (0.7x)
- Computes observability costs (CloudWatch logs, metrics, alarms)
- Includes NAT Gateway if new VPC
- Compares with Heroku billing baseline (if available)
- Classifies complexity tier (small/medium/large) with timeline
- Generates cost optimization opportunities
- Writes `estimation-infra.json` to `$MIGRATION_DIR`

---

## Step 2: Handle Unpriced Services

If the tool returns `unpriced_services` (non-empty list), those services had no cached pricing.

For each unpriced service, call the `awspricing` MCP server:
```
get_pricing(service_code=<service>, filters=[...])
```

Update `estimation-infra.json` with the retrieved prices. If `awspricing` MCP is unavailable, leave as unpriced with a warning.

---

## Step 3: Report to User

Present the estimate summary:

- "**AWS projected:** $X/month (balanced) | $Y/month (optimized with Savings Plans)"
- If Heroku baseline available: "**vs Heroku:** $Z/month → **savings of $N/month ($M/year)**"
- "**Complexity:** [tier] — estimated [timeline]"
- If optimizations available: list applicable Savings Plans / Spot opportunities
- If unpriced services: note which services need manual pricing verification

---

## Scope Boundary

**This phase covers cost estimation ONLY.**

FORBIDDEN — Do NOT include ANY of:
- Terraform code generation
- Migration execution plans or runbooks
- Architecture changes (design is locked)
