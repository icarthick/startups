---
_assemble: assemble-preferences
_of_phase: clarify
_reads:
  - interview (fragment contribution)
_produces:
  - preferences.json
---

# Clarify — Assemble and Validate preferences.json

> **Assembler unit.** Runs after the interview fragment (`clarify-interview.md`)
> has collected and interpreted the answers. It assembles the final
> `preferences.json`, enforces the validation checklist + completion handoff gate,
> and updates `.phase-status.json`. It owns the artifact-level contract for this
> phase.

---

## Step 4: Assemble and Write preferences.json

Assemble all interpreted answers into the final `$MIGRATION_DIR/preferences.json`.
Set `metadata.timestamp` to the current time.

Write `$MIGRATION_DIR/preferences.json`:

```json
{
  "migration_id": "<from .phase-status.json>",
  "skill": "render-to-aws",
  "metadata": {
    "timestamp": "<ISO timestamp>",
    "clarify_mode": "full|fast_path",
    "questions_asked": ["Q1", "Q2", "..."],
    "questions_defaulted": ["Q7", "Q8", "..."],
    "questions_skipped_not_applicable": ["Q6", "Q8", "..."]
  },
  "global": {
    "target_region": "<Q1 value>",
    "compliance": "<Q2 value>",
    "availability": "<Q3 value>",
    "maintenance_window": "<Q4 value>",
    "environment_naming": "<Q5 value>",
    "migration_urgency": "<Q5b value>",
    "migration_approach": "<Q6b value or null if no postgres>",
    "interim_cutover": false,
    "target_exit_date": "<ISO date or null>",
    "ktlo_warning": "<warning text or null>"
  },
  "data": {
    "database_ha": "<Q6 value or omit if no postgres>",
    "migration_method": "<Q6c value or omit if no postgres>",
    "estimated_db_size_gb": "<derived or user-provided or omit if no postgres>",
    "db_size_source": "plan_derived|user_override",
    "redis_ha": "<Q7 value or omit if no key_value>",
    "dns_strategy": "<Q10 value>",
    "cron_target": "<Q8 value or omit if no cron_job>"
  },
  "operational": {
    "container_registry": "<Q12 value>",
    "log_retention_days": "<Q13 value>",
    "alerting": "<Q14 value>",
    "cost_optimization": "<Q15 value>"
  },
  "design_constraints": {
    "web_compute_target": "<Q9 value: elastic_beanstalk|ecs-fargate; omit if no web_service>",
    "eb_deploy_method": {
      "value": "<Q11 value: github_actions|codepipeline|manual; omit if no EB web target>",
      "chosen_by": "user|default"
    }
  },
  "defaults_applied": ["<list of defaulted question IDs>"],
  "sources": {
    "Q1": "user|default",
    "Q2": "user|default"
  }
}
```

Do **not** write a `workshop` object from Clarify. The what-if workshop
(`references/phases/workshop/`) creates/patches `preferences.workshop` later
(`cpu_architecture`, `active`, `active_scenario_id`, `last_sheet_at`). See
`references/shared/schema-workshop-scenarios.md`.

### Schema Rules

1. The `sources` object records how each question was answered: `"user"` (explicitly
   answered) or `"default"` (system default applied, including skipped questions and
   "use defaults for the rest").
2. `defaults_applied` is the array of question IDs that received default values.
3. `metadata.questions_skipped_not_applicable` records questions skipped because their
   triggering condition was not met (e.g., Q6 skipped because no postgres service).
4. Only write keys with non-null values. Omit sections/keys that are entirely null.
5. `global.migration_approach` is `null` when no postgres services present (Q6b not fired).
6. `data.database_ha`, `data.migration_method`, `data.estimated_db_size_gb`,
   `data.db_size_source` are omitted entirely when no postgres service is present.
7. `data.redis_ha` is omitted entirely when no key_value service is present.
8. `data.cron_target` is omitted entirely when no cron_job service is present.
9. `design_constraints.web_compute_target` is omitted when no web_service is present.
10. `design_constraints.eb_deploy_method` is required when `web_compute_target` is
    `"elastic_beanstalk"` or absent (and web_service exists); omit for all-Fargate
    web target.
11. Omit `workshop` on Clarify assemble — workshop mode owns that object.

---

## Validation Checklist

Before handing off to Design:

- [ ] `preferences.json` written to `$MIGRATION_DIR/`
- [ ] `global.target_region` is populated with a valid AWS region code
- [ ] `global.availability` is populated
- [ ] `global.migration_urgency` is populated
- [ ] If postgres in inventory → `data.database_ha` is populated
- [ ] If postgres in inventory → `global.migration_approach` is populated
- [ ] If postgres in inventory → `data.migration_method` is populated
- [ ] If `migration_approach` is `interim_cutover_data_first` → `global.target_exit_date` is a valid future ISO date
- [ ] If `migration_approach` is `interim_cutover_data_first` → `global.interim_cutover` is `true`
- [ ] If cron_job in inventory → `data.cron_target` is one of `"lambda"` or `"fargate_scheduled"`
- [ ] If web_service in inventory → `design_constraints.web_compute_target` is populated
- [ ] If `web_compute_target` is `"elastic_beanstalk"` (or absent, with web_service) → `design_constraints.eb_deploy_method.value` is one of `"github_actions"`, `"codepipeline"`, `"manual"`
- [ ] If `design_constraints.eb_deploy_method` is present → `design_constraints.eb_deploy_method.chosen_by` is `"user"` or `"default"`
- [ ] `operational.container_registry` is populated
- [ ] `operational.log_retention_days` is a positive integer
- [ ] `operational.alerting` is populated
- [ ] `operational.cost_optimization` is one of `"conservative"`, `"balanced"`, `"aggressive"`
- [ ] All entries in `sources` have a value of `"user"` or `"default"`
- [ ] `metadata.clarify_mode` is set to `"fast_path"` or `"full"`
- [ ] Only keys with non-null values are present
- [ ] Output is valid JSON

---

## Completion Handoff Gate (Fail Closed)

The completion checks are declared in this phase's `_postconditions` frontmatter and
enforced per `INTERPRETER.md` § Gate protocol: re-read `preferences.json` from disk,
run the mechanical checks (`_check_file_exists` / `_validate_json`) and the `_assert`
judgment checks (all Validation Checklist items; the postgres/interim-cutover/cron/web
conditionals), then emit `GATE_FAIL` (STOP; do not patch artifacts) or
`HANDOFF_OK | phase=clarify | artifacts=preferences.json` and advance.

---

## Step 5: Update Phase Status and Hand Off

Only after `HANDOFF_OK`, apply the phase-status update protocol (`INTERPRETER.md`
§ The interpreter loop) — mark `phases.clarify` completed and advance per
`_advances_to` — in the **same turn** as the output message below.

Output to user: "Clarification complete. Proceeding to Phase 3: Design AWS Architecture."
