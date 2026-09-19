---
_assemble: assemble-estimate
_of_phase: estimate
_reads:
  - cost-engine fragment contribution
_produces:
  - estimation-infra.json
---

# Estimate — Assemble and Write estimation-infra.json

> **Assembler unit.** Runs after the cost-engine fragment. Writes `estimation-infra.json`,
> presents the financial summary, and offers the optional what-if workshop sidebar.

---

## Step 6: Write estimation-infra.json

Write `$MIGRATION_DIR/estimation-infra.json`:

```json
{
  "migration_id": "<from .phase-status.json>",
  "skill": "render-to-aws",
  "phase": "estimate",
  "timestamp": "<ISO timestamp>",
  "complexity_tier": "<small|medium|large>",
  "pricing_source": "<live|cached_fallback>",
  "current_render_monthly_estimate": {
    "amount": null,
    "source": "unavailable",
    "note": "Verify at render.com/pricing"
  },
  "projected_costs": {
    "aws_monthly_premium": 0,
    "aws_monthly_balanced": 0,
    "aws_monthly_optimized": 0,
    "currency": "USD",
    "period": "monthly"
  },
  "cost_breakdown": [
    {
      "service_id": "<design service_id>",
      "render_service": "<name>",
      "aws_service": "<service type>",
      "monthly_usd": 0,
      "breakdown": {}
    }
  ],
  "recommendation": {
    "path": "migrate_optimized|migrate_phased|stay",
    "path_label": "<human-readable path label>",
    "migrate_if": ["<reason 1>", "..."],
    "stay_if": ["<reason 1>", "..."]
  },
  "warnings": []
}
```

Recommendation logic:

- If `aws_monthly_balanced < current_render_monthly_estimate × 0.8` → path: `"migrate_optimized"`, label: "Migrate — 20%+ savings projected"
- If `aws_monthly_balanced < current_render_monthly_estimate × 1.2` → path: `"migrate_phased"`, label: "Migrate — roughly cost-neutral, strong operational benefits"
- If render baseline unavailable → path: `"migrate_phased"`, label: "Migrate — Render pricing unavailable for comparison"
- Always include both `migrate_if` and `stay_if` reasons

---

## Step 7: Present Financial Summary

Present a user-facing summary table:

```
## Estimated Monthly AWS Costs

| Scenario           | Monthly (USD) |
| ------------------ | ------------- |
| Premium (no savings) | $X.XX       |
| Balanced (recommended) | $X.XX     |
| Optimized (aggressive) | $X.XX    |

Current Render estimate: $X.XX/month* (* from render-pricing-cache.md — verify at render.com/pricing)
Projected savings (balanced): $X.XX/month ($X.XX/year)

Complexity tier: [small/medium/large]
Pricing source: [live / cached AWS rates ±5-10%]

Top cost drivers:
1. [Service name]: $X.XX/month
2. [Service name]: $X.XX/month
3. [Service name]: $X.XX/month
```

---

## Step 8: Workshop Offer + Deferred Advance

After presenting the financial summary, offer the what-if workshop:

```
What would you like to do next?

[A] Enter the what-if workshop — reprice with different region, HA, compute target, or CPU architecture (x86 vs Graviton)
[B] Proceed to Generate migration artifacts
```

- If user picks **A** → Set `phases.workshop` to `"in_progress"`. Load `references/phases/workshop/workshop.md`. Do NOT advance `current_phase` to generate yet — outer Estimate defers this until workshop is resolved.
- If user picks **B** → Set `phases.workshop` to `"completed"` (declined). Advance `current_phase` to `generate`.

This is the **deferred advance**: `current_phase` stays at `estimate` until workshop is resolved (per `SKILL.md § Workshop resume`). The assembler does not advance `current_phase` unconditionally on `HANDOFF_OK` — it defers to the workshop gate.

---

## Step 9: Completion Gate and Phase Status

Re-read `estimation-infra.json`. Verify all `_postconditions` from `estimate.md`. Emit `HANDOFF_OK | phase=estimate` on success, then apply the phase-status update protocol marking `phases.estimate` as `"completed"`.
