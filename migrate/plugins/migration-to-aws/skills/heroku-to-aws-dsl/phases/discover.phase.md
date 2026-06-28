---
# ============================================================================
# discover.phase.md — Phase 1 (Discover).
# THIN phase: frontmatter = phase-level contract; the BODY is composed of
# FRAGMENTS + one ASSEMBLER (the unit taxonomy — see ../INTERPRETER.md).
#
# Fragments are units of work, each authored in its own file under
# phases/discover/ with its OWN frontmatter (scope, produces, postconditions):
#   - terraform [required, always] — independent discoverer (parse IaC)
#   - billing   [optional, glob]   — independent discoverer (parse invoices)
# Fragments WRITE their artifact files to disk directly (terraform creates
# heroku-resource-inventory.json; billing creates billing-profile.json). The
# ASSEMBLER (discover-assemble) then READS those and MUTATES the inventory in
# place to fold in billing + validate. One creator per artifact; assembler-only
# mutation. (NOT in-memory accumulators — fragments produce real on-disk
# artifacts, which is right for large discovery outputs.)
# ============================================================================
_phase: discover
_title: "Discover Heroku Resources"
_requires_phase: null
_scope: >
  Inventory what exists on Heroku from local files (.tf, Procfile, app.json) and
  optional billing exports. ONLY this. No AWS service names, no recommendations,
  no cost estimates for AWS, no Terraform generation, no clustering/dependency
  graphs, no effort estimates.

_input:
  - "**/*.tf"
  - "Procfile"
  - "app.json"
  - "**/*billing*.{csv,json}"
  - "**/*invoice*.{csv,json}"

_init:
  _init_migration_run: true

_re_entry_guard:
  if: "preferences.json exists AND phase clarify completed"
  action: _halt_and_inform
  reason: stale_downstream
  on_confirm: >
    Reset phases clarify, design, estimate, generate, feedback to "pending"
    in .phase-status.json (leave discover as the active in_progress phase),
    and remove their downstream artifacts from $MIGRATION_DIR/ if present:
    preferences.json, preferences-draft.json, aws-design.json,
    estimation-infra.json, generation-warnings.json, the terraform/,
    kubernetes/ and scripts/ directories, MIGRATION_GUIDE.md, README.md,
    and feedback.json. Then run discover normally. NEVER perform this reset
    without the user's explicit confirmation of the re-run.

_preconditions:
  - _check_single_active_phase: true
    _on_failure:
      _halt_and_inform: >
        Another core phase is already in_progress. At most one phase may be
        active at a time. Resolve the active phase before re-running discover.
  - _check_source_exists: { glob: "**/*.tf", containing: 'resource "heroku_' }
    _on_failure:
      _unrecoverable: >
        No Terraform files with heroku_* resources found. Heroku Terraform is
        required for discovery; Procfile/app.json alone are not sufficient.

# Phase body: fragments (units of work) + one assembler (combines/validates).
# terraform [required] and billing [optional] are independent discoverers (two
# sources, two reasons-to-change) writing their data; the assembler merges into
# the single inventory artifact and owns its artifact-level contract.
_fragments:
  - _id: terraform
    _trigger: { _check_source_exists: { glob: "**/*.tf", containing: 'resource "heroku_' } }
    _file: phases/discover/discover-terraform.md
  - _id: billing
    _trigger: { _glob: ["**/*billing*.{csv,json}", "**/*invoice*.{csv,json}"] }
    _file: phases/discover/discover-billing.md

_assemble:
  _file: phases/discover/discover-assemble.md

_postconditions:
  # Phase-level / cross-cutting only. Per-fragment checks live in the fragment
  # files; per-artifact (schema, forbidden-fields) checks live in the assembler.
  - _check_file_exists: heroku-resource-inventory.json
  - _assert: "metadata.discovery_sources reflects which fragments actually ran"

_produces: [heroku-resource-inventory.json]
_advances_to: clarify
_forbids_files: [README.md, discovery-summary.md, "*.txt", discovery-log.md, EXECUTION_REPORT.txt]

_on_error:
  _warn_and_skip:   { effect: "record parse_warning; skip block/file/row; continue", status: continue }
  _halt_and_inform: { effect: "stop; surface diagnostic",                            status: retain_in_progress }
  _unrecoverable:   { effect: "stop; surface error",                                 status: revert_to_pending }
---

# Discover Heroku Resources

## Orientation

Scan the workspace for Heroku declarations and assemble a single flat
`heroku-resource-inventory.json` in `$MIGRATION_DIR/`. The work is composed of
FRAGMENTS (units of work, each its own file) + one ASSEMBLER:

1. **terraform** fragment (`phases/discover/discover-terraform.md`) — primary,
   trigger always-true in practice. Scans `.tf`, integrates Procfile/app.json,
   writes the terraform-derived resource data.
2. **billing** fragment (`phases/discover/discover-billing.md`) — optional. Runs
   only if a billing/invoice file matches its glob trigger. Writes billing data.
   Never fails the phase.
3. **assemble** (`phases/discover/discover-assemble.md`) — the mandatory
   assembler. Merges the fragment outputs into `heroku-resource-inventory.json`
   and owns the artifact-level contract (schema, forbidden-fields, metadata).

Run the fragments in `_fragments` order (skipping a fragment whose trigger is
false — and not even loading its `_file`), then the assembler. Each fragment
and the assembler is a first-class DSL unit with its OWN frontmatter (scope,
produces, postconditions) — read each file to see its contract; this phase only
composes them and owns lifecycle + cross-cutting checks.

After the assembler produces/validates the artifact, the phase
`_postconditions` run; on full pass the interpreter emits
`HANDOFF_OK | phase=discover | ...`, sets `phases.discover="completed"`,
`current_phase="clarify"`, and tells the user to load `clarify.phase.md` next.
