---
_fragment: cost-engine
_of_phase: estimate
_contributes:
  - cost breakdown per service (consumed by estimate-assemble.md)
---

# Estimate Phase: Cost Engine Fragment

> Self-contained cost computation sub-file. Reads `aws-design.json` and the loaded
> pricing data, computes monthly cost for each designed AWS service, and produces a
> cost breakdown map. The assembler (`estimate-assemble.md`) writes `estimation-infra.json`.

**Execute ALL steps in order. Do not skip or deviate.**

---

## Step 0: Load Pricing Mode

Load `references/vendored/estimate/pricing-mode.md` and follow its Step 0 procedure to
determine pricing mode (`live` using awspricing MCP, or `cached` using
`references/vendored/pricing/aws-infra-pricing.json`).

Set `pricing_source`:

- `"live"` — awspricing MCP is available and responding
- `"cached_fallback"` — MCP unavailable after 3 attempts; using cached rates

If `pricing_source == "cached_fallback"`, display:

> ⚠️ awspricing MCP unavailable. Using cached AWS rates (±5-10% accuracy). Add `pricing_source: "cached_fallback"` to estimation-infra.json.

---

## Step 1: Per-Service Cost Computation

For each service in `aws-design.json.services[]`, compute its monthly cost.
All costs are **monthly** USD, rounded to 2 decimal places.

Use `references/vendored/pricing/aws-infra-pricing.json` as the primary pricing source.
Use awspricing MCP for services not in the cached file.

### 1a. Elastic Beanstalk (EC2-backed)

Cost = (EC2 instance rate × hours/month × num_instances) + ALB monthly

- `hours_per_month = 730`
- EC2 rate from: `aws-infra-pricing.json` → EC2 rates table for `aws_config.instance_type` in `preferences.global.target_region`
- ALB from: `estimate-defaults.json.eb_load_balancer_monthly_usd`
- `num_instances = aws_config.min_instances` (sizing baseline)

```
cost_ec2 = ec2_rate_per_hour × 730 × min_instances
cost_alb = estimate_defaults.eb_load_balancer_monthly_usd
total = cost_ec2 + cost_alb
```

### 1b. ECS Fargate (Web Service or Background Worker)

Cost = (Fargate CPU price × vCPU-hours/month) + (Fargate memory price × GB-hours/month) + ALB (if load_balancer == true)

- `fargate_cpu_price_per_vcpu_hour` from `aws-infra-pricing.json` (Fargate rates)
- `fargate_memory_price_per_gb_hour` from `aws-infra-pricing.json`
- `vcpu_count = aws_config.task_cpu / 1024`
- `memory_gb = aws_config.task_memory / 1024`
- `desired_count = aws_config.desired_count`

```
vcpu_hours = vcpu_count × 730 × desired_count
memory_gb_hours = memory_gb × 730 × desired_count
cost_compute = (vcpu_hours × fargate_cpu_price) + (memory_gb_hours × fargate_memory_price)
cost_alb = (aws_config.load_balancer == true) ? estimate_defaults.fargate_alb_monthly_usd : 0
total = cost_compute + cost_alb
```

### 1c. Lambda + EventBridge Scheduler (Cron Job)

Cost = Lambda invocation cost + Lambda duration cost + EventBridge Scheduler cost

Assume: 30 invocations/month for a typical cron (daily job = ~30/month, hourly = ~720/month — use schedule to estimate)

Parse `aws_config.schedule` as a cron expression and estimate monthly invocations:

- `@daily` or `0 0 * * *` → 30/month
- `0 * * * *` (hourly) → 720/month
- Unknown pattern → default 30/month (conservative), add note

```
lambda_memory_gb = aws_config.memory_mb / 1024
duration_seconds = aws_config.timeout_s / 2   # assume 50% of max timeout as avg
gb_seconds_per_invocation = lambda_memory_gb × duration_seconds
total_gb_seconds = gb_seconds_per_invocation × invocations_per_month

# Apply free tier
billable_invocations = max(0, invocations_per_month - estimate_defaults.lambda_free_tier_invocations)
billable_gb_seconds = max(0, total_gb_seconds - estimate_defaults.lambda_free_tier_gb_seconds)

cost_invocations = billable_invocations × 0.0000002   # $0.20 per 1M requests
cost_duration = billable_gb_seconds × 0.0000166667    # $0.0000166667 per GB-second
cost_scheduler = invocations_per_month × estimate_defaults.eventbridge_scheduler_per_invocation_usd
total = cost_invocations + cost_duration + cost_scheduler
```

Note: Lambda pricing effectively $0 for low-frequency crons after free tier.

### 1d. Fargate Scheduled Task (heavy cron)

Same as §1b Fargate compute, but `desired_count = 1` and only billed during execution.
Estimate execution hours = (estimated execution minutes per invocation × invocations) / 60.

### 1e. RDS PostgreSQL

Cost = (instance rate × hours/month) + (storage rate × GB) + (backup storage)

```
instance_rate = rds_rates[aws_config.instance_class][target_region]
cost_instance = instance_rate × 730
cost_storage = aws_config.allocated_storage_gb × 0.115   # gp3 storage per GB/month
cost_backup = aws_config.allocated_storage_gb × 0.095 × 0.1   # 10% backup overhead
total = cost_instance + cost_storage + cost_backup
```

If `multi_az == true`, double the instance cost (Multi-AZ doubles the instance price).

### 1f. Aurora PostgreSQL

```
aurora_instance_rate = aurora_rates[aws_config.instance_class][target_region]
cost_instance = aurora_instance_rate × 730 × (multi_az ? 2 : 1)
cost_storage = aws_config.allocated_storage_gb × 0.10   # Aurora storage per GB/month
cost_io = aws_config.allocated_storage_gb × 0.20 × 0.1   # I/O estimate
total = cost_instance + cost_storage + cost_io
```

### 1g. ElastiCache Redis

```
elasticache_rate = elasticache_rates[aws_config.node_type][target_region]
cost_node = elasticache_rate × 730 × aws_config.num_cache_nodes
total = cost_node
```

### 1h. CloudWatch Logs (per service)

```
log_volume_gb = estimate_defaults.log_volume_gb_per_service   # per service per month
cost_ingest = log_volume_gb × 0.50   # $0.50 per GB ingested
cost_storage = log_volume_gb × (preferences.operational.log_retention_days / 30) × 0.03
total_logs = cost_ingest + cost_storage
```

### 1i. NAT Gateway (shared)

If `new_vpc` mode, add a shared NAT Gateway cost:

```
cost_nat = estimate_defaults.nat_gateway_monthly_usd   # $32/month
```

---

## Step 2: Apply Cost Optimization Tiers

Based on `preferences.operational.cost_optimization`:

```
conservative_multiplier = 1 + estimate_defaults.optimization_savings_ranges.conservative.max_pct / 100
balanced_multiplier = 1 - estimate_defaults.optimization_savings_ranges.balanced.min_pct / 100
optimized_multiplier = 1 - estimate_defaults.optimization_savings_ranges.aggressive.max_pct / 100
```

Produce three total cost figures:

- `aws_monthly_premium`: raw total (conservative, no savings)
- `aws_monthly_balanced`: balanced (5-15% savings from right-sizing)
- `aws_monthly_optimized`: aggressive (15-30% savings)

---

## Step 3: Render Source-Side Baseline (optional)

If `render-resource-inventory.json` has Render plan data and `references/shared/render-pricing-cache.md`
is loaded:

- Sum up the estimated Render monthly cost from the pricing cache
- Set `current_render_monthly_estimate` + note "source-side baseline from render-pricing-cache.md (verify at render.com/pricing)"
- Compute `migration_delta = aws_monthly_balanced - current_render_monthly_estimate`

If no Render pricing data is available, set `current_render_monthly_estimate: null` with `source: "unavailable"`.

---

## Step 4: Classify Complexity Tier

Load `references/vendored/estimate/complexity-tiers.json`. Match the total service count and service types to a tier:

- `small`: ≤5 services total
- `medium`: 6–15 services
- `large`: >15 services OR any specialty services requiring extra design work

Set `complexity_tier` accordingly.

---

## Step 5: Pass to Assembler

Pass the following to `estimate-assemble.md`:

- Per-service cost breakdown map
- Three aggregate totals (premium, balanced, optimized)
- `current_render_monthly_estimate` (or null)
- `complexity_tier`
- `pricing_source`
- Any `warnings[]` from unpriced services or pricing uncertainty
