---
_phase: plan
_title: "Plan Migration Execution"
_requires_phase: estimate
_input:
  - preferences.json
  - estimation-infra.json
  - estimation-ai.json
  - estimation-billing.json
  - aws-design.json
  - aws-design-ai.json
  - aws-design-billing.json
_fragments:
  - _id: plan-infra
    _trigger: { _when: "estimation-infra.json exists" }
    _file: phases/plan/plan-infra.md
  - _id: plan-ai
    _trigger: { _when: "estimation-ai.json exists" }
    _file: phases/plan/plan-ai.md
  - _id: plan-billing
    _trigger: { _when: "estimation-billing.json exists" }
    _file: phases/plan/plan-billing.md
_assemble:
  _file: phases/plan/plan-assemble.md
_produces:
  - { file: generation-infra.json, _when: "infra route active (estimation-infra.json exists)" }
  - { file: generation-ai.json, _when: "AI route active (estimation-ai.json exists)" }
  - { file: generation-billing.json, _when: "billing-only route active (estimation-billing.json exists)" }
_advances_to: generate
_re_entry_guard:
  _stale_if_completed: generate
  _stale_artifact: MIGRATION_GUIDE.md
  _on_reentry: stop_unless_confirmed
  _on_confirm: reset_downstream_to_pending
_preconditions:
  - _check_phase_completed: estimate
    _on_failure: _halt_and_inform
  - _check_single_active_phase: true
    _on_failure: _halt_and_inform
  - _check_file_exists: preferences.json
    _on_failure: _unrecoverable
  - _validate_json: preferences.json
    _on_failure: _unrecoverable
  - _validate_schema: preferences.json
    _on_failure: _unrecoverable
  - _assert: "at least one estimation artifact exists (estimation-infra.json, estimation-ai.json, or estimation-billing.json); if none, Plan cannot run"
    _on_failure: _unrecoverable
  - _validate_schema: estimation-infra.json
    _on_failure: _unrecoverable
  - _validate_schema: estimation-billing.json
    _on_failure: _unrecoverable
  - _validate_schema: estimation-ai.json
    _on_failure: _unrecoverable
_postconditions:
  - _assert: "at least one plan route was active and produced its artifact: infra route -> generation-infra.json; AI route -> generation-ai.json; billing-only route -> generation-billing.json. If no route is active, the phase must not complete"
    _on_failure: _halt_and_inform
  - _assert: "every active route produced valid JSON (each of generation-infra.json / generation-ai.json / generation-billing.json that a triggered route was responsible for exists and parses)"
    _on_failure: _halt_and_inform
  - _assert: "if generation-infra.json exists, its migration timeline, ordering, and risks fields are populated per its schema (the plan is complete enough to generate artifacts from)"
    _on_failure: _halt_and_inform
_forbids_files:
  - README.md
  - MIGRATION_GUIDE.md
  - "*.txt"
  - "terraform/**"
  - "scripts/**"
  - "ai-migration/**"
---

# Phase 5: Plan Migration Execution (Orchestrator)

**Execute ALL steps in order. Do not skip or optimize.**

This phase is driven by the interpreter loop in `INTERPRETER.md`. The entry gate
(estimate completed, single active phase, preferences present + valid, ≥1 estimation
artifact), the `.phase-status.json` write, and the `HANDOFF_OK`/`GATE_FAIL` completion
gate are owned by the interpreter and this phase's frontmatter. The prose below is the
plan **routing procedure**.

Plan turns the estimate + design into an **execution plan** (JSON) — the migration
sequence, timeline, risks, ordering, and TODOs — WITHOUT yet emitting any deployable
code. The downstream `generate` phase builds Terraform, scripts, adapters, and docs
FROM this plan. Splitting them lets the plan be validated and gated before generation
effort is spent, and keeps each fragment reading only upstream artifacts (the plan's
route fragments read the estimate/design; generate's fragments read this phase's
plans).

Each route is a fragment fired by its `_when` trigger and writes its own conditional
plan artifact (see `_produces`). Multiple routes can run in one migration (infra + AI
is a common hybrid); infra and billing-only are mutually exclusive upstream.

## Step 1: Run the Active Plan Routes

Run each route whose `_when` trigger holds (the interpreter loads the fragment only
when its trigger fires). Each reads only its own upstream artifacts:

- **Infrastructure** (`plan-infra.md`) — when `estimation-infra.json` exists. Writes
  `generation-infra.json`.
- **AI** (`plan-ai.md`) — when `estimation-ai.json` exists. Writes `generation-ai.json`.
- **Billing-only** (`plan-billing.md`) — when `estimation-billing.json` exists. Writes
  `generation-billing.json`.

## Step 2: Assemble and Validate

Load `references/phases/plan/plan-assemble.md` (the phase's assembler) and follow it to
enforce the route output gates (≥1 active route produced its plan; infra XOR billing)
and own the phase's artifact-level contract.

## Scope Boundary

**This phase covers migration PLANNING ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Terraform / HCL generation (that is Phase 6 — Generate)
- Migration scripts or runbooks (that is Phase 6 — Generate)
- Provider adapters or test harnesses (that is Phase 6 — Generate)
- Documentation or reports (that is Phase 6 — Generate)
- Re-designing service selections or re-estimating costs (Phases 3–4 are final)

**Your ONLY job: Produce the execution plan JSON. Nothing else.**
