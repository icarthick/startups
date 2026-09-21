---
_fragment: cost-engine
_of_phase: estimate
_contributes:
  - estimation-infra.json (per-service costs, totals, recommendation)
---

# Estimate Phase: Cost Engine

Compute monthly AWS costs for every service in `aws-design.json` services[]. Use the
pricing sources in the order specified; never fabricate rates.

**Pricing source priority:**

1. `references/vendored/pricing/aws-infra-pricing.json` (cached AWS infrastructure rates,
   ±5-10% accuracy).
2. `awspricing` MCP tool (if available) for services not found in the cache.
3. If neither source can price a service: mark it as `"unpriced"` in `warnings[]` and
   exclude from totals. Do NOT estimate or guess.

---

## Step 1: Price Each Service

For each entry in `aws-design.json` services[], compute a monthly USD cost:

### ECS Fargate

```
monthly_cost = (cpu_units/1024 * fargate_cpu_rate + memory_mib/1024 * fargate_memory_rate) * 730
```

Use `aws_config.task_definition.cpu` and `aws_config.task_definition.memory`. Assume 1
task per service unless `worker_count` is set in the Azure service plan config.

### Elastic Beanstalk

Price the EC2 instance type from `aws_config.instance_type` against the On-Demand hourly
rate. Assume 1 instance unless HA is enabled (then 2 for multi-AZ).

`monthly_cost = ec2_hourly_rate * 730 * instance_count`

### RDS (PostgreSQL, SQL Server)

Price the `aws_config.instance_class` using the RDS On-Demand hourly rate.

`monthly_cost = rds_hourly_rate * 730`

Add storage: `aws_config.storage_gb * rds_storage_gb_rate` (default 20 GB if not set).

If `aws_config.multi_az == true`: multiply instance cost by 2.

### S3

Use `aws_config.estimated_storage_gb` if set; else default to 50 GB.

`monthly_cost = storage_gb * s3_standard_rate`

### Lambda

For consumption plan: `monthly_cost = 0` (within free tier for dev-scale). Note in
warnings if usage pattern is unknown.

For provisioned concurrency: price per provisioned concurrency unit per hour × 730.

### ElastiCache (Redis)

Price the `aws_config.node_type` against the ElastiCache On-Demand hourly rate.

`monthly_cost = elasticache_hourly_rate * 730`

### Secrets Manager

Price at `$0.40/secret/month` per Key Vault mapped, plus `$0.05/10,000 API calls`.
Default estimate: `0.40 * num_key_vaults`.

### VPC

No direct cost for VPC itself. NAT Gateway if HA multi-AZ: `$32/month` per NAT gateway
(one per AZ for HA). Note NAT data transfer not included.

---

## Step 2: Compute Totals

```
aws_monthly_balanced = sum(per-service costs, excluding unpriced)
aws_monthly_dev = aws_monthly_balanced (already at dev sizing)
```

Classify `complexity_tier` using `references/vendored/estimate/complexity-tiers.json`.

---

## Step 3: Produce Recommendation

Set `recommendation.path`:

- `migrate_optimized` if AWS cost is ≤80% of Azure estimate OR significant architectural
  benefit (managed services, reduced ops overhead).
- `migrate_phased` if migration complexity is `medium` or `large`.
- `stay` (rare) — only if specific blocker prevents migration.

Always set:

- `recommendation.migrate_if`: array of at least 2 reasons to migrate.
- `recommendation.stay_if`: array of at least 1 reason to stay or pause.
- `recommendation.path_label`: human-readable label (e.g. "Migrate and optimise").

Pass to `estimate-assemble.md`. Do NOT update `.phase-status.json` from this fragment.
