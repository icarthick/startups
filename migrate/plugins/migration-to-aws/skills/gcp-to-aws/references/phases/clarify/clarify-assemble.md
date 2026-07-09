---
_assemble: assemble-preferences
_of_phase: clarify
_reads:
  - interview (fragment contribution)
_produces:
  - preferences.json
---

# Clarify — Assemble preferences.json

> **Assembler unit.** Runs after the `interview` fragment has gathered and
> interpreted all answers. It assembles the final `preferences.json`, applies the
> schema rules, and runs the Validation Checklist that is this phase's
> artifact-level contract. See `clarify.md` for how this unit is composed into the
> phase.

**Execute ALL steps in order. Do not skip or deviate.**

## Step 5: Assemble and Write preferences.json

Assemble all interpreted answers from the completed batches into the final `$MIGRATION_DIR/preferences.json`. If `preferences-draft.json` exists, use it as the base — merge in the final batch's answers, remove the draft-specific metadata fields (`draft`, `batches_completed`, `batches_remaining`), and set `metadata.timestamp` to the current time. Write `$MIGRATION_DIR/preferences.json`:

```json
{
  "metadata": {
    "migration_type": "full",
    "timestamp": "<ISO timestamp>",
    "discovery_artifacts": ["gcp-resource-inventory.json", "ai-workload-profile.json"],
    "questions_asked": [
      "Q1",
      "Q2",
      "Q3",
      "Q5",
      "Q6",
      "Q7",
      "Q16",
      "Q17",
      "Q19",
      "Q21",
      "Q22"
    ],
    "questions_defaulted": ["Q9"],
    "questions_skipped_extracted": ["Q14"],
    "questions_skipped_early_exit": ["Q8"],
    "questions_skipped_not_applicable": ["Q4", "Q10", "Q11", "Q12", "Q13", "Q13b"],
    "detected_settings": [
      {
        "key": "availability",
        "value": "multi-az",
        "source": "terraform:availability_type=REGIONAL",
        "questions_skipped": ["Q6"],
        "confirmed": true,
        "corrected_by_user": false
      }
    ],
    "category_e_enabled": false,
    "clarify_mode": "full",
    "inventory_clarifications": {}
  },
  "design_constraints": {
    "target_region": { "value": "us-east-1", "chosen_by": "user" },
    "compliance": { "value": ["hipaa"], "chosen_by": "user" },
    "gcp_monthly_spend": { "value": "$5K-$20K", "chosen_by": "user" },
    "funding_stage": { "value": "series-a", "chosen_by": "user" },
    "availability": { "value": "multi-az", "chosen_by": "default" },
    "cutover_strategy": { "value": "maintenance-window-weekly", "chosen_by": "user" },
    "kubernetes": { "value": "eks-or-ecs", "chosen_by": "user" },
    "database_traffic": { "value": "steady", "chosen_by": "user" },
    "db_io_workload": { "value": "medium", "chosen_by": "user" },
    "db_size": { "value": "10-100GB", "chosen_by": "user" }
  },
  "ai_constraints": {
    "ai_framework": { "value": ["direct"], "chosen_by": "extracted" },
    "ai_monthly_spend": { "value": "$500-$2K", "chosen_by": "user" },
    "ai_priority": { "value": "balanced", "chosen_by": "user" },
    "ai_critical_feature": { "value": "function-calling", "chosen_by": "user" },
    "ai_token_volume": { "value": "low", "chosen_by": "user" },
    "ai_model_baseline": { "value": "claude-sonnet-4-6", "chosen_by": "user" },
    "ai_vision": { "value": "text-only", "chosen_by": "user" },
    "ai_latency": { "value": "important", "chosen_by": "user" },
    "ai_complexity": { "value": "moderate", "chosen_by": "user" },
    "ai_capabilities_required": {
      "value": ["text_generation", "streaming", "function_calling"],
      "chosen_by": "extracted"
    }
  }
}
```

### Schema Rules

1. Every entry in `design_constraints` and `ai_constraints` is an object with `value` and `chosen_by` fields.
2. `chosen_by` values: `"user"` (explicitly answered), `"default"` (system default applied — includes "I don't know" answers), `"extracted"` (inferred from inventory), `"derived"` (computed from combination of answers + detected capabilities).
3. Only write a key to `design_constraints` / `ai_constraints` if the answer produces a constraint. Absent keys mean "no constraint — Design decides."
4. Do not write null values.
5. For billing-source inventories, `metadata.inventory_clarifications` records Category B answers.
6. `metadata.questions_skipped_early_exit` records questions skipped due to early-exit logic (e.g., Q8 skipped because Q5=multi-cloud).
7. `metadata.questions_skipped_extracted` records questions skipped because inventory already provided the answer.
8. `metadata.detected_settings` records each auto-detected setting with source, confirmation status, and whether the user corrected it in Step 2.5.
9. `metadata.questions_skipped_not_applicable` records questions skipped because the relevant service wasn't in the inventory.
10. `ai_constraints` section is present ONLY if Category F fired. Omit entirely if no AI artifacts exist.
11. `ai_constraints.ai_capabilities_required` is the UNION of detected capabilities from `ai-workload-profile.json` + critical feature from Q17 + vision from Q20. `chosen_by` is `"derived"`.
12. `ai_constraints.ai_framework` is an array (Q14 is select-all-that-apply). If auto-detected, `chosen_by` is `"extracted"`.

After writing `preferences.json`, delete `$MIGRATION_DIR/preferences-draft.json` if it exists.

---

## Validation Checklist

Before handing off to Design:

- [ ] If extractions were made, Step 2.5 detected-settings confirmation was shown and user responded before questions
- [ ] If extractions were made, `metadata.detected_settings` records each inferred value with `confirmed` status
- [ ] If `bigquery_present` was **true**, the Step 4 BigQuery specialist advisory was shown before questions — **or**, if Step 0 option A (reuse preferences), the same advisory was shown after BigQuery detection
- [ ] `preferences.json` written to `$MIGRATION_DIR/`
- [ ] `design_constraints.target_region` is populated with `value` and `chosen_by`
- [ ] `design_constraints.availability` is populated when Cloud SQL PostgreSQL/MySQL is in inventory (asked, extracted, or defaulted — Design must not run with absent/null availability)
- [ ] Only keys with non-null values are present in `design_constraints`
- [ ] Every entry in `design_constraints` and `ai_constraints` has `value` and `chosen_by` fields
- [ ] Config gap answers recorded in `metadata.inventory_clarifications` (billing mode only)
- [ ] Early-exit skips recorded in `metadata.questions_skipped_early_exit`
- [ ] `ai_constraints` section present ONLY if Category F fired
- [ ] If Category F fired, `ai_constraints.ai_framework` is populated (from detection or Q14)
- [ ] If Category F fired, `ai_capabilities_required` is derived from detection + Q17 + Q20
- [ ] `ai_constraints.ai_framework` is an array (Q14 is multi-select)
- [ ] Output is valid JSON
- [ ] `preferences-draft.json` has been deleted (if it existed)
- [ ] `metadata.clarify_mode` is set to `"fast_path"`, `"simple_hybrid"`, or `"full"`

---
