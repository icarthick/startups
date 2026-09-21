---
_phase: clarify
_title: "Clarify Requirements"
_requires_phase: discover
_input:
  - azure-resource-inventory.json
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
  - _check_file_exists: azure-resource-inventory.json
    _on_failure: _unrecoverable
  - _validate_json: azure-resource-inventory.json
    _on_failure: _unrecoverable
_postconditions:
  - _check_file_exists: preferences.json
    _on_failure: _halt_and_inform
  - _validate_json: preferences.json
    _on_failure: _halt_and_inform
  - _assert: "all Validation Checklist items in clarify-assemble.md pass"
    _on_failure: _halt_and_inform
  - _assert: "if azure-resource-inventory.json contains a postgresql or sql_database resource, then data.database_ha is set (non-null)"
    _on_failure: _halt_and_inform
_forbids_files:
  - README.md
  - "*.txt"
  - aws-design.json
  - "terraform/**"
---

# Phase 2: Clarify Requirements

**Phase 2 of 5** — Ask adaptive questions before design begins, then interpret answers
into ready-to-apply design constraints.

> **HARD GATE — Clarify before Design:** Do not load `references/phases/design/design.md`
> (or any later phase) until this phase finishes **and** `$MIGRATION_DIR/.phase-status.json`
> records `phases.clarify` as `"completed"`. If the user asks to skip questions, use
> documented defaults and still complete this phase.

The output — `preferences.json` — is consumed directly by Design and Estimate without
further interpretation.

---

## Step 1: Run the Interview

Load `references/phases/clarify/clarify-interview.md` and follow it. It handles the
prior-run check, selects the active question set, and presents the questions in progressive
batches — interpreting each answer. It contains the full Question Catalog and Defaults Table.

---

## Step 2: Assemble and Validate

Load `references/phases/clarify/clarify-assemble.md` (the phase's assembler) and follow it
to assemble the final `preferences.json`, run the validation checklist + completion handoff
gate, and update `.phase-status.json`.

---

## Scope Boundary

**This phase covers requirements gathering ONLY.**

FORBIDDEN — Do NOT include detailed AWS architecture, code migration examples, cost
calculations, migration timelines, or Terraform generation.

**Your ONLY job: Understand what the user needs. Nothing else.**
