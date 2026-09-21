---
_assemble: estimate
_of_phase: estimate
_produces:
  - estimation-infra.json
---

# Estimate Phase: Assembler

Assemble the cost engine output into `estimation-infra.json`, present the summary, and
update `.phase-status.json`.

---

## Step 1: Build estimation-infra.json

Conform to `references/vendored/estimate/estimation-infra.schema.json`:

```json
{
  "phase": "estimate",
  "timestamp": "<ISO 8601>",
  "complexity_tier": "small|medium|large",
  "projected_costs": {
    "aws_monthly_balanced": 0,
    "aws_monthly_dev": 0,
    "azure_monthly_estimate": null,
    "currency": "USD",
    "pricing_source": "cached|live_mcp|cached_fallback"
  },
  "per_service_costs": [],
  "recommendation": {
    "path": "migrate_optimized|migrate_phased|stay",
    "path_label": "",
    "migrate_if": [],
    "stay_if": []
  },
  "warnings": []
}
```

Set `projected_costs.azure_monthly_estimate` only if the user provided Azure billing data
or the `azure-pricing-cache.md` contains matching resource rates. Do not fabricate Azure costs.

---

## Step 2: Validation

1. `projected_costs.aws_monthly_balanced` is a positive number.
2. `recommendation.path` is one of `migrate_optimized`, `migrate_phased`, `stay`.
3. `recommendation.migrate_if` and `recommendation.stay_if` are non-empty arrays.
4. `complexity_tier` is one of `small`, `medium`, `large`.
5. Every service in `aws-design.json` services[] appears in `per_service_costs[]` or in
   `warnings[]` as unpriced.
6. `aws_monthly_balanced` equals the arithmetic sum of priced `per_service_costs`.

---

## Step 3: Write estimation-infra.json

Write to `$MIGRATION_DIR/estimation-infra.json`.

---

## Step 4: Present Cost Summary

Present to the user:

```
## Estimate Summary

**Complexity:** <tier>
**Estimated monthly AWS cost:** $<aws_monthly_balanced> USD (dev sizing)
<If azure estimate available:> **Estimated current Azure cost:** $<azure_monthly_estimate> USD

**Recommendation:** <path_label>

**Migrate if:** <migrate_if bullets>
**Stay if:** <stay_if bullets>

<If any unpriced services:> Note: N service(s) could not be priced from available data.
```

---

## Step 5: Offer Feedback Sidebar

If `phases.feedback` is `"pending"`, present the feedback offer (see SKILL.md § Feedback
Sidebar). Resolve before proceeding to Generate.

---

## Step 6: Update .phase-status.json

Set `phases.estimate` to `"completed"` and `current_phase` to `"generate"` in
`$MIGRATION_DIR/.phase-status.json`.

Emit: `HANDOFF_OK | phase=estimate`
