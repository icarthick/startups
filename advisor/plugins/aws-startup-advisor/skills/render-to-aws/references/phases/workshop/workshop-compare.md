---
_fragment: compare
_of_phase: workshop
_trigger: { _when: "user chose Compare scenarios OR after a successful refresh" }
_contributes:
  - user-facing comparison table (no new files written)
---

# Workshop Phase: Compare Scenarios

> Presents a side-by-side comparison table of all priced scenarios.

**Execute ALL steps in order. Do not skip or deviate.**

---

## Step 1: Load All Scenario Manifests

Read `scenarios/index.json`. For each scenario in `scenarios[]`, read its manifest file
(`scenarios/scenario-NNN.json`) to get the `estimation_summary`.

---

## Step 2: Build Comparison Table

Present the comparison as a table, one column per scenario. Mark the active scenario with ★:

```
## Scenario Comparison

| Metric                  | Baseline (001)       | Scenario 002 ★        | Scenario 003         |
| ----------------------- | -------------------- | --------------------- | -------------------- |
| Label                   | baseline             | arm64 + us-west-2     | fargate-all          |
| Region                  | us-east-1            | us-west-2             | us-east-1            |
| Web target              | Elastic Beanstalk    | Elastic Beanstalk     | Fargate              |
| CPU arch                | x86_64               | arm64                 | x86_64               |
| Availability            | multi-az             | multi-az              | multi-az             |
| Monthly premium (USD)   | $X.XX                | $X.XX                 | $X.XX                |
| Monthly balanced (USD)  | $X.XX                | $X.XX                 | $X.XX                |
| Monthly optimized (USD) | $X.XX                | $X.XX                 | $X.XX                |
| vs Baseline (balanced)  | —                    | -$X.XX (N%)           | +$X.XX (N%)          |
| Pricing source          | cached               | cached                | cached               |

Render estimate (baseline): $X.XX/month* (* render-pricing-cache.md — verify at render.com/pricing)

★ = active scenario (will be used for Generate)
```

If any scenario used `pricing_source: "cached_fallback"` and a different region, show:

> ⚠️ Region-based pricing: Rate differences for non-us-east-1 regions require awspricing MCP. These estimates use us-east-1 cached rates — actual costs in [region] may differ by ±5-15%.

---

## Step 3: Present Actions

After the table:

```
[1] Create another scenario — return to the assumption sheet
[2] Set active scenario — choose which scenario to use for Generate
[3] Exit to Generate — use the current active scenario (★)
```

- **[1]** → Return to `workshop-sheet.md`
- **[2]** → Ask "Enter scenario ID to make active (e.g., scenario-002):", validate, update `active_scenario_id`, restore that scenario's preference/design/estimate files to the working tree, update `preferences.workshop.active_scenario_id`
- **[3]** → Load `workshop-assemble.md`
