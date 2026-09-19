---
_fragment: sheet
_of_phase: workshop
_contributes:
  - active scenario preferences (patched into preferences.json by workshop-refresh.md)
---

# Workshop Phase: Assumption Sheet

> Presents the current scenario's knobs and lets the user apply changes before repricing.

**Execute ALL steps in order. Do not skip or deviate.**

---

## Step 1: Capture Baseline (first entry only)

If `scenarios/index.json` does not exist, run the baseline capture:

1. Create `$MIGRATION_DIR/scenarios/` directory.
2. Copy current `preferences.json` → `scenarios/scenario-001.preferences.json`
3. Copy current `aws-design.json` → `scenarios/scenario-001.aws-design.json`
4. Copy current `estimation-infra.json` → `scenarios/scenario-001.estimation-infra.json`
5. Write `scenarios/scenario-001.json` (manifest):
   ```json
   {
     "scenario_id": "scenario-001",
     "label": "baseline",
     "created_at": "<ISO timestamp>",
     "source": "baseline",
     "preferences_subset": {},
     "estimation_summary": {
       "aws_monthly_premium": <from estimation-infra.json>,
       "aws_monthly_balanced": <from estimation-infra.json>,
       "aws_monthly_optimized": <from estimation-infra.json>,
       "complexity_tier": "<from estimation-infra.json>",
       "pricing_source": "<from estimation-infra.json>"
     },
     "paths": {
       "preferences": "scenarios/scenario-001.preferences.json",
       "aws_design": "scenarios/scenario-001.aws-design.json",
       "estimation_infra": "scenarios/scenario-001.estimation-infra.json"
     }
   }
   ```
6. Write `scenarios/index.json`:
   ```json
   {
     "baseline_scenario_id": "scenario-001",
     "active_scenario_id": "scenario-001",
     "max_scenarios": 5,
     "inventory_fingerprint": "<sha256 of render-resource-inventory.json>",
     "scenarios": [
       {
         "scenario_id": "scenario-001",
         "label": "baseline",
         "created_at": "...",
         "source": "baseline",
         "manifest": "scenarios/scenario-001.json"
       }
     ]
   }
   ```
7. Patch `preferences.workshop`:
   ```json
   "workshop": {
     "active": true,
     "cpu_architecture": "x86_64",
     "last_sheet_at": "<ISO timestamp>",
     "active_scenario_id": "scenario-001"
   }
   ```

---

## Step 2: Present the Assumption Sheet

Display the current active scenario's assumptions as a table:

```
## What-If Workshop — Assumption Sheet

Active scenario: [label] ([scenario_id])
Baseline: scenario-001

| Knob              | Current Value                          | Change?      |
| ----------------- | -------------------------------------- | ------------ |
| AWS Region        | [global.target_region]                 | [A]          |
| Availability/HA   | [global.availability]                  | [B]          |
| Web Service target| [compute_target.default]               | [C]          |
| Cron target       | [operational.cron_target]              | [D]          |
| CPU Architecture  | [workshop.cpu_architecture]            | [E]          |

Actions:
[1] Apply changes & reprice  — runs inner Design+Estimate with the patched preferences
[2] Compare all scenarios    — side-by-side table of all priced scenarios
[3] Exit to Generate         — leave workshop, proceed with the active scenario
[4] Exit to full re-Clarify  — ⚠️  resets Design/Estimate (requires confirmation)
```

---

## Step 3: Collect Knob Changes

Wait for the user to specify which knobs to change and their new values.

**Region change:**

- Valid: any valid AWS region code (e.g., `us-west-2`, `eu-central-1`)
- Patch: `preferences.global.target_region = "<new region>"`
- Note: "Region pricing differences require awspricing MCP. Without it, rate delta is ±0% (us-east-1 cache stays)."

**Availability change:**

- Valid: `single-az`, `multi-az`, `multi-az-ha`, `multi-region`
- Patch: `preferences.global.availability = "<value>"`
- Cascade: also patch `preferences.data.database_ha` if not explicitly overridden

**Web Service compute target:**

- Valid: `elastic_beanstalk`, `ecs-fargate`
- Patch: `preferences.design_constraints.compute_target.default = "<value>"`

**Cron target:**

- Valid: `lambda_eventbridge`, `fargate_scheduled` (only if cron_job services present)
- Patch: `preferences.operational.cron_target = "<value>"`

**CPU Architecture:**

- Valid: `x86_64`, `arm64`
- Patch: `preferences.workshop.cpu_architecture = "<value>"`
- Note: arm64/Graviton instances generally offer 10-20% better price-performance

After collecting all changes, record `preferences_subset` (changed dot-paths only).

---

## Step 4: Route to Action

- User picks **[1]** → Load `workshop-refresh.md` with the patched preferences.
- User picks **[2]** → Load `workshop-compare.md`.
- User picks **[3]** → Load `workshop-assemble.md`.
- User picks **[4]** → Confirm: "This will mark Design and Estimate as stale. Continue?" If yes → re-entry guard → reset downstream → re-run Clarify.
