---
_fragment: interview
_of_phase: clarify
_scope: >
  Run the adaptive question interview against the discovered inventory and write
  preferences.json. ONLY this — requirements gathering, no AWS configs, no cost,
  no sizing, no Terraform. Does NOT update .phase-status.json.
_produces: [preferences.json]
_postconditions:
  - _validate_json: preferences.json
  - _assert: "metadata.clarify_mode is 'full' or 'fast_path'"
  - _assert: "global.target_region is a valid AWS region code; global.availability is set"
  - _assert: "design_constraints.kubernetes.value is one of eks-managed, eks-or-ecs, ecs-fargate; chosen_by is user or default"
  - _assert: "every entry in sources has value 'user' or 'default'"
  - { _assert: "preferences-draft.json deleted if it existed", _on_failure: _warn_and_skip }
_on_error:
  _default_and_warn: { effect: "apply documented default; record source=default; continue", status: continue }
  _halt_and_inform:  { effect: "stop; surface diagnostic",                                  status: retain_in_progress }
  _unrecoverable:    { effect: "stop; surface error",                                       status: revert_to_pending }
---

# Clarify Fragment: Interview

## Orientation

The single clarify-phase FRAGMENT (this phase has one responsibility: run the
interview). Triggered always by `clarify.phase.md`. It reads
`heroku-resource-inventory.json` and the question set in
`knowledge/clarify/clarify-questions.json`, runs the adaptive question flow, and
CREATES `preferences.json` in `$MIGRATION_DIR/` (the assembler validates it
afterward). This is a DATA-DRIVEN driver: the question prompts, options,
triggers, defaults, validations, batch composition, and fast-path config are all
in the questions JSON — the steps below are the ALGORITHM that iterates that
data; they do not inline the catalog or defaults. The output artifact SHAPE is
the contract in `schemas/preferences.schema.json`.

## Step: prior_draft_check

```meta
_when: "preferences-draft.json exists in $MIGRATION_DIR/"
```

A partial set of answers from a previous session exists (the phase-level
`_re_entry_guard` already handled the completed-downstream-design case; this step
handles only an in-flight DRAFT, which invalidates nothing downstream).

Read `preferences-draft.json`. Tell the user:

> "I found a partial set of answers from a previous session ([N] of [total]
> batches completed). Would you like to:
> A) Resume — I'll pick up the remaining questions
> B) Start fresh and re-answer all questions"

- **A (resume):** keep the draft as the working base; read
  `metadata.batches_completed` to know which batches are done, and SKIP those
  completed batches when you reach `present_batches`.
- **B (fresh):** delete `preferences-draft.json` and proceed as a clean run.

(If no draft exists, this step is skipped entirely.)

## Step: read_inventory_and_summarize

```meta
_writes_var: inventory_facts
```

Read `heroku-resource-inventory.json` (guaranteed present by the phase
preconditions). Present a discovery summary to the user:

> **Apps discovered:** [metadata.total_apps_discovered] Heroku apps
> **Resource types:** [count of formations], [addons], [spaces], [pipelines]
> **Top add-on services:** [top 3–5 addon `config.addon_service` by frequency]
> **Heroku generation:** [Cedar/Fir/Mixed — summarize apps[].heroku_generation]

If `billing_profile.available == true`, also show:

> **Monthly Heroku spend:** $[total_monthly_cost] ([billing_period])
> **Top cost categories:** [top 3 line_items by cost]

Record into `inventory_facts` the values listed under `inventory_facts` in
`knowledge/clarify/clarify-questions.json` (derive each from
`heroku-resource-inventory.json` per that file's descriptions): `total_apps`,
`has_postgres`, `has_redis`, `has_kafka`, `has_space`, `peering_detected`,
`peering_vpc_id`, `has_fir`, `postgres_plan`. Later steps reference these by name
to gate questions and the fast path.

## Step: fast_path_gate

```meta
_writes_var: clarify_mode
_knowledge: [knowledge/clarify/clarify-questions.json]
```

Evaluate fast-path eligibility using `fast_path.eligible_when` in
`knowledge/clarify/clarify-questions.json` (against `inventory_facts`).

**If eligible**, offer it using `fast_path.offer_prompt` (fill `{N}` =
`total_apps`) and `fast_path.offer_options`.

- **Yes →** set `clarify_mode = fast_path.clarify_mode_value`. Ask ONLY the
  questions in `fast_path.ask_questions` (plus `Q11` if `fast_path.ask_q11_if`
  holds). Apply each remaining APPLICABLE question's `default` (record in
  `metadata.questions_defaulted` with `source: "default"`), plus the
  `fast_path.extra_defaults`. Then SKIP `present_batches` and go to
  `assemble_preferences`. Inform the user which smart defaults were applied and
  that they can say "I want to change something" to override any.
- **No, or NOT eligible →** set `clarify_mode = "full"` and continue to
  `determine_active_questions`.

## Step: determine_active_questions

```meta
_writes_var: active_questions
_knowledge: [knowledge/clarify/clarify-questions.json]
```

For every question in `knowledge/clarify/clarify-questions.json.questions`,
evaluate its `trigger` against `inventory_facts`: `"always"` is always active;
any other trigger is a plain-language condition over `inventory_facts` (e.g.
`has_postgres`, `peering_detected AND peering_vpc_id is null`). A question whose
trigger is false is INACTIVE. Record inactive questions (trigger false) into
`metadata.questions_skipped_not_applicable`.

Migration approach is the single canonical question **Q6b** (see its
`_canonical_note` in the JSON) — there is no separate Q5b and no "migration
urgency" question.

## Step: present_batches

```meta
_collect: [answers, questions_asked, questions_defaulted]
_knowledge: [knowledge/clarify/clarify-questions.json]
```

Iterate `knowledge/clarify/clarify-questions.json.batches` IN ORDER. For each
batch, present only its ACTIVE questions (from `determine_active_questions`);
skip a batch with no active questions, and skip any batch already covered by
`metadata.batches_completed` (draft resume). See `_batch_notes` in the JSON.

For each active batch, in order:

1. **Present** the batch's active questions per the catalog-driver below (a
   conversational lead-in using the batch `name`; tell the user they can answer,
   skip individual ones, or say "use defaults for the rest").
2. **Wait** for the user's response. Do NOT present the next batch or advance
   without a response or an explicit "use defaults for the rest."
3. **Interpret + validate** each answer per the catalog-driver below (the
   questions JSON is authoritative; honor each question's `validation`,
   `follow_up_when_value`, and default).
4. **Save draft** if MORE batches remain: write/update
   `$MIGRATION_DIR/preferences-draft.json` with all answers so far, including
   `metadata.draft: true`, `metadata.batches_completed`,
   `metadata.batches_remaining`, and a timestamp. Batch name values:
   `"global"`, `"data_network"`, `"operational"`. If this was the LAST active
   batch, do NOT write a draft — proceed to `assemble_preferences`.

### Driving the catalog (no inlined questions — read the JSON)

The question definitions live in
`knowledge/clarify/clarify-questions.json.questions`. For each active question
in the batch, the driver uses that question's entry:

- **Present** it using `prompt` + `options` (label/value pairs). The lead-in
  context is the batch `name`; tell the user they may answer, skip (default
  applies), or say "use defaults for the rest."
- **Interpret** the answer to the option's `value` and write it to the entry's
  `writes` path in `preferences.json`. The JSON is AUTHORITATIVE for semantics
  and option values — do NOT improvise. Some entries carry extra handling the
  driver MUST honor: `validation` (reject + re-prompt on bad format, e.g. Q9/Q9b
  subnet/VPC regexes), `follow_up_when_value` (e.g. Q6b interim-cutover → ask the
  exit date, validate, set the `then_set` fields), `size_hint` (Q6c), and
  `design_impact` notes.
- **Default** a skipped question to its `default` (record `source: "default"`).
  A `default` of `null` with a `no_default_note` means the question has NO
  default and MUST be answered when active (Q9/Q9b).

**"Use defaults for the rest"** at any point: apply each remaining unanswered/
remaining-batch active question's `default` (record `source: "default"`) and skip
directly to `assemble_preferences`.

## Step: assemble_preferences

```meta
_writes: preferences.json
```

Assemble all interpreted answers into `$MIGRATION_DIR/preferences.json`. Use the
current wall-clock time (ISO 8601 UTC) for `metadata.timestamp`. If
`preferences-draft.json` was used as a base, merge in the final batch's answers
and DROP the draft-only metadata fields (`draft`, `batches_completed`,
`batches_remaining`).

Write `preferences.json` with this shape (omit any key/section whose value is
null — see schema rules):

```json
{
  "migration_id": "<from .phase-status.json>",
  "skill": "heroku-to-aws",
  "metadata": {
    "timestamp": "<ISO timestamp>",
    "clarify_mode": "full|fast_path",
    "questions_asked": ["Q1", "Q2"],
    "questions_defaulted": ["Q7"],
    "questions_skipped_not_applicable": ["Q8"]
  },
  "global": {
    "target_region": "...",
    "compliance": "...",
    "availability": "...",
    "maintenance_window": "...",
    "environment_naming": "...",
    "migration_approach": "...",
    "interim_cutover": false,
    "target_exit_date": null,
    "ktlo_warning": null,
    "fir_intent": null
  },
  "data": {
    "database_ha": "...",
    "migration_method": "...",
    "estimated_db_size_gb": "...",
    "db_size_source": "plan_derived|user_override",
    "redis_ha": true,
    "kafka_retention_days": 7,
    "dns_strategy": "..."
  },
  "network": {
    "existing_vpc_id": null,
    "subnet_ids": [],
    "private_space_detected": false
  },
  "operational": {
    "container_registry": "...",
    "containerization_status": "...",
    "log_retention_days": 30,
    "alerting": "...",
    "cost_optimization": "..."
  },
  "design_constraints": {
    "kubernetes": { "value": "ecs-fargate", "chosen_by": "user|default" }
  },
  "defaults_applied": ["Q7"],
  "sources": { "Q1": "user|default", "Q2": "user|default" }
}
```

**Schema rules** (the assembler enforces these):

1. `sources` records how each question was answered: `"user"` (explicitly) or
   `"default"` (default applied — includes skips and "defaults for the rest").
2. `defaults_applied` = the array of question IDs that received defaults.
3. `metadata.questions_skipped_not_applicable` = questions skipped because their
   trigger was false (e.g. Q6 skipped because no Postgres).
4. Only write keys with non-null values. Omit entirely-null sections/keys.
5. `global.fir_intent` is null when no Fir apps (Q11 not fired).
6. `network.existing_vpc_id`/`subnet_ids` are null/empty when no peering. Write
   the `network` section (with `private_space_detected: true`) whenever a
   Private Space exists in the inventory (`has_space`), EVEN IF it has no
   peering — a space without peering still sets `private_space_detected: true`
   with null/empty vpc/subnet fields. Omit the `network` section entirely only
   when NO space exists.
7. `data.database_ha`/`redis_ha`/`kafka_retention_days` are OMITTED entirely
   when those services are absent from the inventory.

After writing `preferences.json`, DELETE `preferences-draft.json` if it exists.
