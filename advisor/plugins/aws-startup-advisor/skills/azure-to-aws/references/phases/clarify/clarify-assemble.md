---
_assemble: clarify
_of_phase: clarify
_produces:
  - preferences.json
---

# Clarify Phase: Assembler

Assemble the interview answers into `preferences.json`, validate, and update phase status.

---

## Step 1: Assemble preferences.json

```json
{
  "phase": "clarify",
  "timestamp": "<ISO 8601>",
  "global": {
    "target_region": "<Q1 answer>",
    "high_availability": "<Q3 answer>",
    "region_map": "<Q6 answer or null>"
  },
  "design_constraints": {
    "compute_target": {
      "default": "<Q2 answer: ecs-fargate|elastic_beanstalk>",
      "value": "<Q2 answer: ecs-fargate|elastic_beanstalk>"
    }
  },
  "data": {
    "database_ha": "<Q4 answer or false if no DB resources>"
  },
  "network": {
    "vpc_mode": "<Q5 answer: new_vpc|existing_vpc>",
    "existing_vpc_id": "<Q5 vpc_id or null>"
  },
  "generate": {
    "tf_structure": "<Q7 answer: flat|modular>",
    "include_storage_transfer_guide": "<Q8 answer>"
  }
}
```

---

## Step 2: Validation Checklist

1. `global.target_region` is a non-empty string.
2. `design_constraints.compute_target.default` is one of `ecs-fargate`, `elastic_beanstalk`.
3. `global.high_availability` is a boolean.
4. If inventory has postgresql or sql_database: `data.database_ha` is a boolean (non-null).
5. `network.vpc_mode` is one of `new_vpc`, `existing_vpc`.
6. If `network.vpc_mode == "existing_vpc"`: `network.existing_vpc_id` is a non-empty string.
7. `generate.tf_structure` is one of `flat`, `modular`.

If any check fails: halt, report the specific failure, and ask the user for the missing
value. Do not write a partial file.

---

## Step 3: Write preferences.json

Write the assembled structure to `$MIGRATION_DIR/preferences.json`.

---

## Step 4: Update .phase-status.json

Set `phases.clarify` to `"completed"` and `current_phase` to `"design"` in
`$MIGRATION_DIR/.phase-status.json`.

Emit: `HANDOFF_OK | phase=clarify`
