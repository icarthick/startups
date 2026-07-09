---
_phase: generate
_title: "Generate Migration Artifacts"
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
    _file: phases/generate/generate-infra.md
  - _id: plan-ai
    _trigger: { _when: "estimation-ai.json exists" }
    _file: phases/generate/generate-ai.md
  - _id: plan-billing
    _trigger: { _when: "estimation-billing.json exists" }
    _file: phases/generate/generate-billing.md
_assemble:
  _file: phases/generate/generate-assemble.md
_produces:
  - { file: generation-infra.json, _when: "infra route active (estimation-infra.json exists)" }
  - { file: generation-ai.json, _when: "AI route active (estimation-ai.json exists)" }
  - { file: generation-billing.json, _when: "billing-only route active (estimation-billing.json exists)" }
  - { file: terraform/, _when: "infra artifact route active (generation-infra.json AND aws-design.json exist)" }
  - { file: scripts/, _when: "infra artifact route active (generation-infra.json AND aws-design.json exist)" }
  - { file: validation-report.json, _when: "infra artifact route active" }
  - { file: ai-migration/, _when: "AI artifact route active (generation-ai.json AND aws-design-ai.json exist)" }
  - { file: terraform/skeleton.tf, _when: "billing artifact route active (generation-billing.json AND aws-design-billing.json exist)" }
  - MIGRATION_GUIDE.md
  - README.md
  - { file: migration-report.html, _when: "artifact validation passed (report is optional, non-blocking on validation failure)" }
_advances_to: complete
_preconditions:
  - _check_phase_completed: estimate
    _on_failure: _halt_and_inform
  - _check_single_active_phase: true
    _on_failure: _halt_and_inform
  - _check_file_exists: preferences.json
    _on_failure: _unrecoverable
  - _validate_json: preferences.json
    _on_failure: _unrecoverable
  - _assert: "at least one estimation artifact exists (estimation-infra.json, estimation-ai.json, or estimation-billing.json); if none, Generate cannot run"
    _on_failure: _unrecoverable
_postconditions:
  - _check_file_exists: [MIGRATION_GUIDE.md, README.md]
    _on_failure: _halt_and_inform
  - _assert: "Stage 1 route gates pass: for each estimation artifact present, the matching plan exists — estimation-infra.json -> generation-infra.json; estimation-ai.json -> generation-ai.json; estimation-billing.json -> generation-billing.json"
    _on_failure: _halt_and_inform
  - _assert: "Stage 2 route gates pass: if the infra artifact route is active (generation-infra.json AND aws-design.json) then terraform/, scripts/, and validation-report.json (status in {passed, passed_degraded_offline, skipped_user_continue}) exist; if the AI artifact route is active (generation-ai.json AND aws-design-ai.json) then ai-migration/ exists; if the billing artifact route is active (generation-billing.json AND aws-design-billing.json) then terraform/skeleton.tf exists"
    _on_failure: _halt_and_inform
  - _assert: "MIGRATION_GUIDE.md has Prerequisites and Verification sections; README.md lists the generated artifacts"
    _on_failure: _halt_and_inform
  - _assert: "no unresolved placeholder tokens remain in generated Terraform .tf files (variable references belong in variables as var.* references)"
    _on_failure: _halt_and_inform
_forbids_files:
  - preferences.json
  - aws-design.json
  - aws-design-ai.json
  - aws-design-billing.json
  - estimation-infra.json
  - estimation-ai.json
  - estimation-billing.json
---

# Phase 5: Generate Migration Artifacts (Orchestrator)

**Execute ALL steps in order. Do not skip or optimize.**

This phase is driven by the interpreter loop in `INTERPRETER.md`. The entry gate
(estimate completed, single active phase, preferences present + valid, ≥1 estimation
artifact), the `.phase-status.json` write, and the `HANDOFF_OK`/`GATE_FAIL` completion
gate are owned by the interpreter and this phase's frontmatter. The prose below is the
generate **procedure**.

## Overview

Generate runs in **two stages**:

1. **Stage 1 — Migration Planning** (the `plan-*` fragments): each active route turns
   its estimation + design artifacts into an execution plan (`generation-*.json`).
   Fragments are independent — each reads only its own upstream artifacts.
2. **Stage 2 — Artifact Generation** (the assembler, `generate-assemble.md`): reads
   the Stage 1 plans + designs and derives the deployable artifacts — `terraform/`,
   `scripts/`, `ai-migration/`, the always-on docs, and the optional HTML report.
   Because Stage 2 depends on Stage 1's output, it lives in the assembler (which is
   allowed to read fragment output), not in a second set of fragments (fragments
   never read each other's output — `INTERPRETER.md` § the unit kinds).

Multiple routes can run independently; infra and billing-only are mutually exclusive
upstream (Design/Estimate already enforced that).

## Stage 1: Migration Planning (the `plan-*` fragments)

Run each planning route whose `_when` trigger holds (the interpreter loads the
fragment only when its trigger fires). Each reads only its own upstream artifacts:

- **Infrastructure** (`generate-infra.md`) — when `estimation-infra.json` exists.
  Writes `generation-infra.json`.
- **AI** (`generate-ai.md`) — when `estimation-ai.json` exists. Writes
  `generation-ai.json`.
- **Billing-only** (`generate-billing.md`) — when `estimation-billing.json` exists.
  Writes `generation-billing.json`.

## Stage 2: Artifact Generation + Completion (the assembler)

Load `references/phases/generate/generate-assemble.md` (the phase's assembler) and
follow it. **Stage 2 depends on Stage 1's plans**, so it lives in the assembler (the
only unit allowed to read fragment output). It derives the deployable artifacts from
the plans + designs — `terraform/`, `scripts/`, `ai-migration/`, the billing skeleton,
the always-on docs (`MIGRATION_GUIDE.md`, `README.md`), and the optional HTML report
— loading the `generate-artifacts-*.md` sub-files for each active route. It also
carries the dirty-state resumability tracking and owns the phase's completion gate
(Stage 1 + Stage 2 route gates, documentation gate). It emits `HANDOFF_OK | phase=generate`
on pass and advances to `complete`.

## Summary

**Use structured completion reporting** (see `shared/artifact-validation.md` Section 3). Present final summary to user:

```
Phase 5 (Generate) complete.

✓ Produced:
  - generation-infra.json: [X]-week migration plan
  - terraform/: [N] files (list key files)
  - scripts/: [N] files
  - MIGRATION_GUIDE.md: [N] sections
  - README.md: artifact catalog + quick start
  - migration-report.html: executive summary
  - migration-report.pdf: PDF version [or "skipped — no converter available"]

⊘ Skipped (not applicable):
  - [artifact]: [reason]

⚠ Skipped (non-blocking failure):
  - migration-report.html: [failure reason]  ← only if report generation failed
```

After the structured block, include:

1. **Plans generated** — List all `generation-*.json` files produced
2. **Artifacts generated** — List all directories and files created (terraform/, scripts/, ai-migration/, MIGRATION_GUIDE.md, README.md). Include `migration-report.html` only if it exists.
3. **Validation status** — If `$MIGRATION_DIR/validation-report.json` exists, report its `status` field (`passed`, `passed_degraded_offline`, or `skipped_user_continue`). If `status == "passed_degraded_offline"`, add: "Provider registry was unreachable; `terraform validate` was skipped. Re-run `terraform init && terraform validate` from a network-connected shell to complete validation."
4. **Key timelines** — Highlight migration timeline from the generation plans
5. **Key risks** — Highlight top risks from the generation plans
6. **TODO markers** — Note any TODO markers in generated artifacts that require manual attention
7. **Next steps** — Recommend reviewing generated artifacts, customizing TODO sections, and beginning migration execution

Output to user:

- If `migration-report.html` exists: "Migration artifact generation complete. All phases of the GCP-to-AWS migration analysis are complete. Your migration report is ready at $MIGRATION_DIR/migration-report.html"
- If `migration-report.html` is missing: "Migration artifact generation complete. All phases of the GCP-to-AWS migration analysis are complete. Markdown documentation is available at $MIGRATION_DIR/MIGRATION_GUIDE.md and $MIGRATION_DIR/README.md. (HTML report generation is optional and non-blocking.)"
