# Infrastructure Estimate Schema

Schema for `estimation-infra.json`, produced by `estimate-infra.md`.

---

## Cost tiers (`projected_costs` / `cost_comparison`)

The fields **`aws_monthly_premium`**, **`aws_monthly_balanced`**, **`aws_monthly_optimized`** (under `projected_costs`) and **`option_a_premium`**, **`option_b_balanced`**, **`option_c_optimized`** (under `cost_comparison`) are **three pricing scenarios** for the **same** GCP->AWS mapping in `aws-design.json`. They are **not** three alternative Terraform roots.

| Tier key        | User-facing label | Subtitle (use in reports / MIGRATION_GUIDE)                                |
| --------------- | ----------------- | -------------------------------------------------------------------------- |
| **`premium`**   | Premium           | _Highest resilience / highest monthly estimate in this model_              |
| **`balanced`**  | Balanced          | _Default scenario; compare GCP to this first_                              |
| **`optimized`** | Optimized         | _Lower monthly estimate; reservations / Spot / storage trade-offs assumed_ |

**How to read:** Scenario order is **highest -> middle -> lowest** monthly AWS estimate for the modeled architecture. **Balanced** is the **primary** comparison row vs the GCP baseline. **Premium** and **Optimized** are **bounds** (HA vs cost-optimization skew).

**Terraform:** When the Generate phase produces `terraform/`, it implements **one** infrastructure baseline aligned with the **Balanced** scenario (`aligned_with_estimate_tier` in the `migration_summary` output). **Premium** and **Optimized** remain **estimate-only** unless the customer edits IaC. See `references/phases/generate/generate-terraform.md` (`terraform/README.md`, `main.tf` header comment).

---

## estimation-infra.json shape

The artifact SHAPE (all fields, types, the pricing_source enum, projected_costs
scenarios, complexity_tier, and the required set) is defined by the JSON Schema at
`references/vendored/estimate/estimation-infra.schema.json` (canonical, shared across
migration skills) and validated at the estimate completion gate + plan entry gate via
`_validate_schema`. The sections below are the NON-shape contract a schema cannot hold —
cost-tier semantics, the recommendation-path table, observability, and the validation
checklist — and remain the estimate-infra prose.

### recommendation block in estimation-infra.json

The `recommendation` block is the single source of truth for migrate/stay guidance. Consumed by Estimate chat output AND HTML migration report (Section 0). Do not duplicate this logic in the report template.

| `path` value          | `path_label` (display)         |
| --------------------- | ------------------------------ |
| `"migrate_optimized"` | `"Migrate with Optimizations"` |
| `"migrate_phased"`    | `"Phased Migration"`           |
| `"stay"`              | `"Stay on GCP"`                |

Validation:

- `path` is one of: `"migrate_optimized"`, `"migrate_phased"`, `"stay"`
- `path_label` matches the corresponding display string for `path`
- `migrate_if` and `stay_if` are non-empty arrays of strings
- `next_steps` is a non-empty array of strings
- Block is **REQUIRED** in `estimation-infra.json` output (Part 7 must write it)

## Observability Entry in `projected_costs.breakdown`

When Part 2B of `estimate-infra.md` produces an observability cost, it is included as an entry in `projected_costs.breakdown[]` with this shape:

```json
{
  "service": "CloudWatch + X-Ray (Observability)",
  "low": 7.00,
  "mid": 10.00,
  "high": 15.00,
  "accuracy": "±30%",
  "pricing_source": "cached",
  "components": {
    "log_ingestion": 5.00,
    "log_storage": 0.45,
    "custom_metrics": 3.00,
    "alarms": 0.50,
    "tracing": 0.00
  },
  "volume_source": "heuristic",
  "note": "GCP Cloud Operations includes 50 GB/month free logging, free alerting, and free profiling. CloudWatch charges from the first GB."
}
```

**Validation for observability entry:**

- `components` keys are exactly: `log_ingestion`, `log_storage`, `custom_metrics`, `alarms`, `tracing`
- `volume_source` is one of: `"heuristic"`, `"billing"` (reflects log volume source — the largest cost component; metrics are always heuristic regardless of this field)
- `tracing` is 0 when no tracing signals detected in source — do not add X-Ray costs unprompted
- `mid` equals the sum of all `components` values
- This entry REPLACES any CloudWatch/log/metric portion in the "Supporting" row — never both

## Output Validation Checklist

- `design_source` is `"infrastructure"`
- `pricing_source.status` is `"cached"`, `"live"`, `"cached_fallback"`, or `"unavailable"`
- `accuracy_confidence` matches the pricing mode (±5-10% for cached/live, ±15-25% for fallback)
- `current_costs.source` is `"billing_data"` if `billing-profile.json` was used, `"inventory_estimate"`, `"preferences"`, `"user_provided"` (asked during estimate), or `"unavailable"` (user declined) otherwise
- `current_costs.gcp_monthly` matches billing-profile.json total (if used) or is a reasonable estimate
- `projected_costs` has all three tiers (premium, balanced, optimized)
- **Tier semantics:** Three totals are **scenario $** only (same design); **Balanced** matches generated Terraform baseline — see **Cost tiers** section above; user-facing labels must use the subtitles there (also `estimate-infra.md` Present Summary / `generate-report.md`)
- `projected_costs.breakdown` covers compute, database, storage, networking, supporting services, and observability
- Every service in `aws-design.json` is represented in the cost breakdown
- `projected_costs.breakdown` observability entry (when present) REPLACES any CloudWatch/log/metric costs in the "Supporting" row — never double-count
- `cost_comparison` shows all three options with monthly and annual differences
- `cost_comparison.commitment_context` is present if `billing-profile.json` has `commitments.has_active_cuds == true`; omitted otherwise
- `migration_cost_considerations.billing_data_available` is `true` if `billing-profile.json` exists, `false` otherwise
- If `billing_data_available` is `true`: `migration_cost_considerations.categories` lists **GCP vendor egress / data transfer** only (never human or professional-services costs)
- If `billing_data_available` is `false`: `migration_cost_considerations.categories` is empty; `note` explains that billing data is required for GCP egress fee estimates
- `roi_analysis` presents recurring monthly/annual savings (or increase) per tier
- `roi_analysis` is honest — if migration increases cost, say so and justify with non-cost benefits
- `optimization_opportunities` only includes strategies relevant to the designed architecture
- Each `optimization_opportunities[]` entry includes required fields: `opportunity`, `target_services`, `savings_percent`, `implementation_effort`, `description`. Optional fields: `type`, `savings_monthly` (null when post-migration sizing unavailable), `commitment`, `timing`, `prerequisite`, `references`, `alternative`
- Compute Savings Plans entries for Cloud Run migrations MUST NOT include `savings_monthly` sized from GCP billing — use `savings_monthly: null` and `timing: post-migration`
- Database Savings Plans entries MAY include `savings_monthly` only when projected DB on-demand exceeds $50/month
- `optimization_opportunities` savings are incremental to **Balanced** on-demand totals — not additive on **Optimized** tier (which already embeds reservation/Spot assumptions)
- `financial_summary` provides a clear executive-level view
- `recommendation` block exists with `path`, `path_label`, `migrate_if`, `stay_if`, and `next_steps` all populated
- `recommendation.path` is one of: `"migrate_optimized"`, `"migrate_phased"`, `"stay"`
- `recommendation.next_steps` includes actionable items
- No references to AI-specific costs (those belong in `estimate-ai.md`)
- No references to billing-only estimates (those belong in `estimate-billing.md`)
- All cost values are numbers, not strings
- Output is valid JSON
