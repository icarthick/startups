---
# ============================================================================
# clarify.phase.md — Phase 2 (Clarify).
# THIN phase: frontmatter = phase-level contract; the BODY is composed of
# FRAGMENTS + one ASSEMBLER (the unit taxonomy — see ../INTERPRETER.md).
#
# This is the first "single linear job" phase: its work is ONE responsibility
# (run the adaptive interview, write preferences.json), so the taxonomy shape is
#   - ONE fragment  : clarify-interview  — the interactive Q&A; CREATES preferences.json
#   - ONE assembler : clarify-assemble   — NO-OP / PROMOTE; validates the
#                     artifact-level contract (schema + conditional checklist).
# This validates the taxonomy on a single-fragment phase (the assembler earns
# its mandatory existence as a pure validator — it reads the fragment's artifact
# and owns its final contract, even though it neither mutates nor creates).
#
# Clarify is the ONE phase that stays LLM-driven judgment end-to-end: there is
# no arithmetic here, only interpreting answers into design constraints. The
# DSL's job is the lifecycle/contract scaffolding (gate, re-entry, schema), not
# the conversation — the conversation is the fragment's prose.
# ============================================================================
_phase: clarify
_title: "Clarify Requirements"
_requires_phase: discover
_scope: >
  Ask the adaptive question set, interpret answers into ready-to-apply design
  constraints, and write a single preferences.json. ONLY this. No AWS service
  configurations, no cost calculations, no dyno->Fargate sizing, no Terraform
  generation, no migration timelines. Requirements gathering ONLY.

_input:
  - heroku-resource-inventory.json

_knowledge:
  - { file: knowledge/clarify/clarify-questions.json }

_re_entry_guard:
  if: "aws-design.json exists AND phase design completed"
  action: _halt_and_inform
  reason: stale_downstream
  on_confirm: >
    Reset phases design, estimate, generate, feedback to "pending" in
    .phase-status.json (leave clarify as the active in_progress phase), and
    remove their downstream artifacts from $MIGRATION_DIR/ if present:
    aws-design.json, estimation-infra.json, generation-warnings.json, the
    terraform/, kubernetes/ and scripts/ directories, MIGRATION_GUIDE.md,
    README.md, and feedback.json. preferences.json itself is NOT removed — the
    re-run overwrites it. Then run clarify normally. NEVER perform this reset
    without the user's explicit confirmation of the re-run.

_preconditions:
  - _check_single_active_phase: true
    _on_failure:
      _halt_and_inform: >
        Another core phase is already in_progress. At most one phase may be
        active at a time. Resolve the active phase before re-running clarify.
  - _check_phase_completed: discover
    _on_failure:
      _halt_and_inform: >
        Discover has not completed. Run Phase 1 (discover.phase.md) first —
        clarify reads heroku-resource-inventory.json.
  - _check_file_exists: heroku-resource-inventory.json
    _on_failure:
      _unrecoverable: >
        heroku-resource-inventory.json is missing. It is produced by discover
        and is required to determine which questions apply.
  - _validate_json: heroku-resource-inventory.json
    _on_failure:
      _unrecoverable: >
        heroku-resource-inventory.json does not parse as valid JSON. Re-run
        discover to regenerate it.

# Phase body: ONE fragment (the interview) + one assembler (validator no-op).
# Single responsibility -> single fragment; the assembler is mandatory and here
# is a pure validator (reads preferences.json, owns its artifact-level contract).
_fragments:
  - _id: interview
    _trigger: { _always: true }
    _file: phases/clarify/clarify-interview.md

_assemble:
  _file: phases/clarify/clarify-assemble.md

_postconditions:
  # Phase-level / cross-cutting only. The fragment owns write-time interview
  # correctness; the assembler owns the artifact-level schema + conditional
  # checklist contract. The phase just confirms the artifact exists.
  - _check_file_exists: preferences.json
  - _assert: "preferences-draft.json no longer exists in $MIGRATION_DIR/"

_produces: [preferences.json]
_advances_to: design
_forbids_files:
  - README.md
  - clarify-summary.md
  - "*.txt"
  - aws-design.json
  - MIGRATION_GUIDE.md

_on_error:
  _default_and_warn: { effect: "apply documented default; record source=default; continue", status: continue }
  _halt_and_inform:  { effect: "stop; surface diagnostic",                                  status: retain_in_progress }
  _unrecoverable:    { effect: "stop; surface error",                                       status: revert_to_pending }
---

# Clarify Requirements

## Orientation

Ask the adaptive question set tailored to the discovered inventory, interpret
the answers into ready-to-apply design constraints, and write a single
`preferences.json` in `$MIGRATION_DIR/`. The output is consumed DIRECTLY by
Design and Estimate with no further interpretation.

The work is composed of ONE FRAGMENT + one ASSEMBLER (the unit taxonomy — see
`../INTERPRETER.md`):

1. **interview** fragment (`phases/clarify/clarify-interview.md`) — the single
   unit of work, trigger always-true. Reads the inventory, runs the fast-path
   gate / progressive batches / question catalog, handles draft resume, and
   CREATES `preferences.json`. This is the LLM-driven conversation; the prose in
   that file is authoritative for HOW the interview runs.
2. **assemble** (`phases/clarify/clarify-assemble.md`) — the mandatory
   assembler. A NO-OP / PROMOTE: it creates and mutates nothing
   (`_mutates: []`, `_produces: []`), it READS `preferences.json` and owns the
   artifact-level contract (schema validity + the conditional validation
   checklist that depends on what the inventory contained).

Run the fragment, then the assembler. Each is a first-class DSL unit with its
OWN frontmatter — read each file for its contract; this phase only composes them
and owns lifecycle + cross-cutting checks.

After the assembler validates the artifact, the phase `_postconditions` run; on
full pass the interpreter emits `HANDOFF_OK | phase=clarify | ...`, sets
`phases.clarify="completed"`, `current_phase="design"`, and tells the user to
load `design.phase.md` next.
