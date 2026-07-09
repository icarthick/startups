---
_phase: clarify
_title: "Clarify Requirements"
_requires_phase: discover
_input:
  - gcp-resource-inventory.json
  - gcp-resource-clusters.json
  - ai-workload-profile.json
  - billing-profile.json
  - migration-preview.json
_fragments:
  - _id: interview
    _trigger: { _always: true }
    _file: phases/clarify/clarify-interview.md
_assemble:
  _file: phases/clarify/clarify-assemble.md
_produces:
  - preferences.json
_advances_to: design
_re_entry_guard:
  _stale_if_completed: design
  _stale_artifact: aws-design.json
  _on_reentry: stop_unless_confirmed
  _on_confirm: reset_downstream_to_pending
_preconditions:
  - _check_phase_completed: discover
    _on_failure: _halt_and_inform
  - _check_single_active_phase: true
    _on_failure: _halt_and_inform
  - _assert: "at least one discovery artifact exists (gcp-resource-inventory.json, ai-workload-profile.json, or billing-profile.json)"
    _on_failure: _unrecoverable
_postconditions:
  - _check_file_exists: preferences.json
    _on_failure: _halt_and_inform
  - _validate_json: preferences.json
    _on_failure: _halt_and_inform
  - _validate_schema: preferences.json
    _on_failure: _halt_and_inform
  - _assert: "all Validation Checklist items in clarify-assemble.md pass"
    _on_failure: _halt_and_inform
  - _assert: "preferences.json has design_constraints.region set (all migration types); for a full migration design_constraints is populated, for an AI-only migration ai_constraints is fully populated and design_constraints is limited to region"
    _on_failure: _halt_and_inform
  - _assert: "if BigQuery was detected in discovery (google_bigquery_* in IaC and/or BigQuery billing rows), the BigQuery specialist advisory was surfaced and preferences records bigquery_present true"
    _on_failure: _halt_and_inform
  - _assert: "if ai-workload-profile.json exists, ai_constraints reflects the F-category / AI-only answers (model priority, latency, agentic migration_approach where applicable)"
    _on_failure: _halt_and_inform
_forbids_files:
  - README.md
  - "*.txt"
  - aws-design.json
  - "terraform/**"
---

# Phase 2: Clarify Requirements

**Phase 2 of 6** — Ask adaptive questions before design begins, then interpret answers into ready-to-apply design constraints.

This phase is driven by the interpreter loop in `INTERPRETER.md`. The entry gate
(discover completed, single active phase, a discovery artifact present), the
`.phase-status.json` write, and the `HANDOFF_OK`/`GATE_FAIL` completion gate are owned
by the interpreter and this phase's frontmatter. The prose below is the clarify
**procedure** — the category routing, question rules, and answer interpretation.

The output — `preferences.json` — is consumed directly by Design and Estimate without
any further interpretation. Clarify is **mandatory** (see SKILL.md); there is no
exception for "quick" or "obvious" migrations. If the user asks to skip questions, use
documented defaults and still complete this phase.

Questions are organized into **six named categories (A–F)** with documented firing
rules (up to 22 questions), presented in **progressive batches** with intermediate
saves. A standalone **AI-Only** flow exists for migrations that only move AI/LLM calls
to Bedrock. All of that routing, question text, and interpretation lives in the
interview fragment below.

---

## Step 1: Run the Interview

Load `references/phases/clarify/clarify-interview.md` and follow it. It handles the
prior-run check, migration-type routing (including the standalone AI-only flow),
fast-path/simple-hybrid eligibility, extraction + the Step 2.5 detected-settings
confirmation gate, category firing rules, and the progressive question batches —
interpreting each answer. It contains the full category routing, the Answer
Combination Triggers, and the Defaults Table.

---

## Step 2: Assemble and Validate

Load `references/phases/clarify/clarify-assemble.md` (the phase's assembler) and follow
it to assemble the final `preferences.json`, apply the schema rules, and run the
Validation Checklist. It owns the artifact-level contract for this phase.

---

## Scope Boundary

**This phase covers requirements gathering ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Detailed AWS architecture or service configurations
- Code migration examples or SDK snippets
- Detailed cost calculations
- Migration timelines or execution plans
- Terraform generation

**Your ONLY job: Understand what the user needs. Nothing else.**
