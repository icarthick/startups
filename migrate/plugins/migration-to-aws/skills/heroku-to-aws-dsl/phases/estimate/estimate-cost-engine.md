---
_fragment: cost-engine
_of_phase: estimate
_scope: >
  Compute per-service AWS costs, observability, tiers, Heroku comparison, ROI,
  complexity tier, optimization opportunities, and recommendation; write
  estimation-infra.json. ONLY this — no design changes, no Terraform, no
  runbooks, no labor cost. Does NOT update .phase-status.json.
_produces: [estimation-infra.json]
_postconditions:
  - _validate_json: estimation-infra.json
  - _assert: "projected_costs.aws_monthly_balanced is a positive number"
  - _assert: "projected_costs.breakdown[] has an entry (or an unpriced warning) for every aws-design service"
  - _assert: "aws_monthly_balanced equals the sum of the per-line balanced costs (Property-16), excluding unpriced lines"
  - _assert: "complexity_tier is small|medium|large"
  - _assert: "recommendation.path is migrate_optimized|migrate_phased|stay with a non-empty path_label and non-empty migrate_if/stay_if"
_on_error:
  _warn_and_skip:    { effect: "record warning; skip this item; continue",            status: continue }
  _default_and_warn: { effect: "apply documented default; record warning; continue",   status: continue }
  _halt_and_inform:  { effect: "stop; surface diagnostic",                             status: retain_in_progress }
  _unrecoverable:    { effect: "stop; surface error",                                  status: revert_to_pending }
---

# Estimate Fragment: Cost Engine

## Orientation

The single estimate-phase FRAGMENT. Triggered always by `estimate.phase.md`.
Reads `aws-design.json`, `preferences.json`, `heroku-resource-inventory.json`,
and the two `knowledge/estimate/*.json` files, then CREATES
`estimation-infra.json` (the assembler validates it). The math is data-driven:
rates + per-service formulas + the multi-AZ convention are in `aws-pricing.json`;
tier/observability/complexity/optimization/recommendation policy is in
`estimate-defaults.json`. Output SHAPE is `schemas/estimation-infra.schema.json`.
Cost results are DIRECT applications of the formulas — apply each as written;
the only judgment is the ROI narrative and recommendation prose.

## Step: select_pricing_source

```meta
_writes_var: pricing_source
_knowledge: [knowledge/estimate/aws-pricing.json, knowledge/estimate/estimate-defaults.json]
```

Per `estimate-defaults.json.pricing_source`: the cached `aws-pricing.json` rates
are the DEFAULT and deterministic source (`status: "cached"`). Check the cache
`_meta.last_updated` vs `staleness_days`: if stale, set `status: "cached_stale"`
and note it (infra rates still reliable). For any service whose rate is NOT in
the cache, follow the hierarchy: IF an awspricing MCP is available, attempt a
live lookup (`live`); on failure fall back to cache (`cached_fallback`); if
neither, mark the service `unavailable` and add to
`pricing_source.services_with_missing_fallback[]`. Record the per-service
`pricing_source` value as you price each service below. (For typical
heroku→aws stacks ALL rates are cached → no MCP needed; this is the path the
cold-test exercises.)

Surface the pricing status to the user before calculating (cache date +
accuracy, or the stale/live/unavailable note).

## Step: heroku_baseline

```meta
_writes_var: current_costs
```

Determine the Heroku monthly baseline (first match wins):

1. `heroku-resource-inventory.json.billing_profile` with `available == true` →
   use `total_monthly_cost` (+ `line_items[]` for per-app breakdown);
   `current_costs.source = "billing_data"`.
2. Else derive from the inventory via the Heroku pricing cache (if present);
   `source = "pricing_cache"`, accuracy ±5%; unmatched plans → warn + exclude.
3. Else ask the user for approximate Heroku monthly spend; `source =
   "user_provided"`.
4. Else `source = "unavailable"` — present AWS costs without comparison.

Set `current_costs.heroku_monthly`, `heroku_annual = monthly * 12` (or null),
`breakdown` (dyno/addon/platform when available), `baseline_note`.

## Step: per_service_costs

```meta
_for_each: design.services
_collect: [breakdown, warnings]
_knowledge: [knowledge/estimate/aws-pricing.json]
```

For each service in `aws-design.json.services[]`, compute its BALANCED monthly
cost by applying the matching `aws-pricing.json` formula. Apply each rate
EXACTLY; do not improvise. **Multi-AZ:** read the service's `multi_az_handling`
and apply it correctly (this is the trap — see the probe):

- `baked_in` (rds_postgresql) → rate ALREADY includes multi-AZ; NEVER multiply.
- `multiplier_x2` (elasticache) → multiply by 2 when the design entry's
  `aws_config.multi_az == true`.
- `intrinsic` (aurora, msk) → no adjustment.

Per service type:

- **Fargate** → `(task_cpu/1024 * per_vcpu_hour + task_memory/1024 *
  per_gb_mem_hour) * hours_per_month * desired_count`.
- **ALB** → `monthly_fixed + per_lcu_hour * hours_per_month`.
- **RDS PostgreSQL** → `instances[instance_class] * hours_per_month + storage_gb
  - storage_per_gb_month` (baked_in: no multi-AZ multiply).
- **Aurora PostgreSQL** → `instances[instance_class] * hours_per_month +
  storage_gb * storage_per_gb_month` (+ I/O if usage data; default 0).
- **ElastiCache Redis** → `nodes[node_type] * hours_per_month * (2 if multi_az
  else 1)`.
- **Amazon MSK** → `brokers[broker_instance_type] * hours_per_month *
  broker_count + storage_per_broker_gb * broker_count * storage_per_gb_month`.
- **Fast-path services** (CloudWatch Logs, S3, SES, EventBridge, MQ, OpenSearch,
  CloudFront, Secrets Manager, ElastiCache Memcached) — use
  `aws-pricing.json.fast_path_services` (flat/minimal estimates; mark these as
  estimates). EXCEPTION: a `CloudWatch Logs` service (e.g. a Papertrail mapping)
  is NOT given its own breakdown line — its logging cost is SUBSUMED into the
  single post-loop observability block (Step `observability_cost`). It still
  counts as PRICED for the every-service-priced gate (record it in the
  observability entry's `note`); do NOT mark it `unpriced`.
- **RDS Proxy** → when a service has `rds_proxy: true`, add the proxy cost.

Append a breakdown entry `{ service, service_id, mid: <balanced>, pricing_source
}` per service. If a rate is `unavailable`, mark the line `pricing_source:
"unpriced"`, EXCLUDE it from the total, and warn (`_warn_and_skip`).

## Step: post_loop_infra_costs

```meta
_collect: [breakdown, warnings]
_knowledge: [knowledge/estimate/aws-pricing.json]
```

Add costs that derive from the design as a whole (NOT per-service loop entries):

- **NAT Gateway** — if `aws-design.json.vpc_design.mode == "new_vpc"` (private
  subnets present): add `nat_gateway.monthly_fixed` (+ data estimate; default 0).
  Add it ONCE here — the EKS branch below must NOT re-add NAT.
- **EKS cluster** — if `aws-design.json` has an `eks_cluster` entry (EKS compute
  path): add `eks.control_plane_monthly` + `node_monthly_rate * node_count`
  where `node_count = eks_cluster.node_groups[0].desired_size` (the steady-state
  count for the balanced tier — NOT min or max), and `node_monthly_rate` =
  `eks.node_rates_monthly[node_groups[0].instance_types[0]]`. NOTE: EKS PODS COST
  $0 — each EKS service in `services[]` is a $0 breakdown line (priced, NOT
  `unpriced`); do NOT add per-pod task costs (compute is billed via the nodes
  here; charging pods double-counts). The web ALB is added by the ALB per-service
  line, and NAT by the NAT bullet above — the EKS branch does NOT re-add ALB or
  NAT. (Design's EKS path emits `eks_cluster`; this fires when it is present.)
- **Route 53** — if `preferences.data.dns_strategy == "route53"`: add
  `route53.hosted_zone_monthly` (+ query estimate).

## Step: observability_cost

```meta
_collect: [breakdown]
_knowledge: [knowledge/estimate/aws-pricing.json, knowledge/estimate/estimate-defaults.json]
```

Add ONE CloudWatch observability entry (post-loop; it is the SINGLE home for all
logging cost — a design `CloudWatch Logs` service does NOT get its own line, it
is subsumed here, so never double-count), per
`estimate-defaults.json.observability`:

- `log_gb` = sum over designed services of
  `estimate-defaults.json.observability.log_volume_gb_per_service` (3/Fargate
  SERVICE — one count per Fargate service regardless of desired_count;
  1/RDS-or-Aurora service, 2/ALB service, 1/NAT, 0.5/ElastiCache service, 2/MSK
  broker). Count PER DESIGNED SERVICE, not per running task.
- `custom_metrics = max(10, service_count*5)`; `alarms = max(5, service_count*2)`.
- `retention_months = preferences.operational.log_retention_days / 30` (default 1).
- `log_ingestion = log_gb*0.50`; `log_storage = log_gb*0.03*retention_months`;
  `metrics_cost = custom_metrics*0.30`; `alarms_cost = alarms*0.10`; `tracing =
  0` unless tracing detected. `total_observability = sum`.
- Add `{ service: "CloudWatch + X-Ray (Observability)", low: total*0.7, mid:
  total, high: total*1.5, accuracy: "±30%", components: {...} }`.

## Step: totals_and_tiers

```meta
_writes_var: projected_costs
_knowledge: [knowledge/estimate/estimate-defaults.json]
```

- `aws_monthly_balanced` = SUM of all breakdown `mid` values, EXCLUDING any
  `unpriced` lines. This is the **Property-16 invariant**: the total MUST equal
  the arithmetic sum of the per-line balanced costs.
- Apply `estimate-defaults.json.tiers` multipliers to the balanced total:
  `aws_monthly_premium = balanced * 1.50`; `aws_monthly_optimized = balanced *
  0.70`. Round each tier monthly to 2dp, THEN multiply by 12 for annual figures
  (round-then-multiply, so stored monthly and annual reconcile):
  `aws_annual_optimized = round(aws_monthly_optimized, 2) * 12`.
- These three are pricing SCENARIOS for the same architecture; Balanced is the
  primary and what generated Terraform aligns to.

## Step: comparison_roi_complexity

```meta
_writes_var: derived
_knowledge: [knowledge/estimate/estimate-defaults.json]
```

- **cost_comparison** (only if a Heroku baseline exists): per tier, `aws_monthly`,
  `monthly_difference = tier - heroku`, `annual_difference = monthly_difference *
  12`, `percent_change`. Omit/null if baseline unavailable.
- **migration_cost_considerations**: per
  `estimate-defaults.json.migration_cost_note` (billing-available vs not).
- **roi_analysis**: monthly/annual differences (balanced + optimized; negative =
  AWS cheaper), plus the qualitative `operational_efficiency_factors` +
  `non_cost_benefits` from defaults (do NOT assign dollar values to these).
- **complexity_tier** + `complexity_inputs`: classify per
  `estimate-defaults.json.complexity_tiers` (evaluate large→medium→small, first
  match). Inputs: `service_count` (= design `metadata.total_services`),
  `monthly_spend` (= balanced), `has_databases` (any service in
  `has_databases_services`), `has_stateful_storage`, `availability` +
  `compliance` (from preferences), `multi_region` (services span 2+ regions).
- **optimization_opportunities[]**: include ONLY catalog entries whose `when`
  holds for THIS design (Compute Savings Plans if Fargate; Database Savings Plans
  if RDS/Aurora and >$50/mo; Fargate Spot if worker tasks; S3-IA if S3). Compute
  `savings_monthly` where the catalog says to.

## Step: recommendation_and_write

```meta
_writes: estimation-infra.json
_knowledge: [knowledge/estimate/estimate-defaults.json]
```

Form the **recommendation** per `estimate-defaults.json.recommendation_logic`:
choose `path` (migrate_optimized / migrate_phased / stay) + its `path_label`,
write a one-sentence `roi_justification`, `confidence`, and stack-specific
`migrate_if` / `stay_if` arrays + `next_steps`.

Assemble the full artifact (shape per `schemas/estimation-infra.schema.json`):
`phase: "estimate"`, `timestamp` (current ISO 8601 UTC), `design_source`,
`pricing_source`, `accuracy_confidence`, `current_costs`, `projected_costs`
(with `breakdown[]`), `cost_comparison`, `migration_cost_considerations`,
`roi_analysis`, `optimization_opportunities`, `complexity_tier`,
`complexity_inputs`, `financial_summary`, `warnings`, `recommendation`. Write it
to `$MIGRATION_DIR/estimation-infra.json`.

Present a concise (<25 line) summary to the user: pricing source + accuracy;
Heroku vs AWS balanced (if available); the three-tier table; per-service
breakdown; complexity tier + timeline; savings; top 2–3 optimizations;
recommendation label + justification.
