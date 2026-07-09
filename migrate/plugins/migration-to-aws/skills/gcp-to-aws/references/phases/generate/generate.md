---
_phase: generate
_title: "Generate Migration Artifacts"
_requires_phase: plan
_input:
  - preferences.json
  - generation-infra.json
  - generation-ai.json
  - generation-billing.json
  - aws-design.json
  - aws-design-ai.json
  - aws-design-billing.json
_fragments:
  - _id: artifacts-infra
    _trigger: { _when: "generation-infra.json AND aws-design.json exist" }
    _file: phases/generate/generate-terraform.md
  - _id: artifacts-scripts
    _trigger: { _when: "generation-infra.json AND aws-design.json exist" }
    _file: phases/generate/generate-scripts.md
  - _id: artifacts-ai
    _trigger: { _when: "generation-ai.json AND aws-design-ai.json exist" }
    _file: phases/generate/generate-ai-artifacts.md
  - _id: artifacts-billing
    _trigger: { _when: "generation-billing.json AND aws-design-billing.json exist" }
    _file: phases/generate/generate-billing-skeleton.md
_assemble:
  _file: phases/generate/generate-assemble.md
_produces:
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
  - _check_phase_completed: plan
    _on_failure: _halt_and_inform
  - _check_single_active_phase: true
    _on_failure: _halt_and_inform
  - _check_file_exists: preferences.json
    _on_failure: _unrecoverable
  - _validate_json: preferences.json
    _on_failure: _unrecoverable
  - _assert: "at least one plan artifact exists (generation-infra.json, generation-ai.json, or generation-billing.json); if none, Generate cannot run"
    _on_failure: _unrecoverable
_postconditions:
  - _check_file_exists: [MIGRATION_GUIDE.md, README.md]
    _on_failure: _halt_and_inform
  - _assert: "each active artifact route produced its tree: infra route (generation-infra.json AND aws-design.json) -> terraform/, scripts/, and validation-report.json (status in {passed, passed_degraded_offline, skipped_user_continue}); AI route (generation-ai.json AND aws-design-ai.json) -> ai-migration/; billing route (generation-billing.json AND aws-design-billing.json) -> terraform/skeleton.tf"
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
  - generation-infra.json
  - generation-ai.json
  - generation-billing.json
---

# Phase 6: Generate Migration Artifacts (Orchestrator)

**Execute ALL steps in order. Do not skip or optimize.**

This phase is driven by the interpreter loop in `INTERPRETER.md`. The entry gate
(plan completed, single active phase, preferences present + valid, ≥1 plan artifact),
the `.phase-status.json` write, and the `HANDOFF_OK`/`GATE_FAIL` completion gate are
owned by the interpreter and this phase's frontmatter. The prose below is the generate
**routing procedure**.

Generate turns the execution plans (`generation-*.json`, produced by the upstream
`plan` phase) + the designs into **deployable artifacts** — Terraform, migration
scripts, AI adapters, docs, and an optional report. Each artifact producer is a
fragment fired by its `_when` trigger; because these read only upstream artifacts (the
plan + design), they are independent fragments. The cross-cutting docs + report, which
must read ALL the generated artifacts, are owned by the assembler.

## Step 1: Run the Active Artifact Fragments

Run each fragment whose `_when` trigger holds (the interpreter loads it only when its
trigger fires):

- **Terraform** (`artifacts-infra` → `generate-terraform.md`) — when
  `generation-infra.json` AND `aws-design.json` exist. Writes `terraform/` and, after
  `terraform validate`, `validation-report.json`.
- **Scripts** (`artifacts-scripts` → `generate-scripts.md`) — same trigger. Writes
  `scripts/`. Reads the plan + design (not the generated `terraform/`), so it is
  independent of the Terraform fragment.
- **AI** (`artifacts-ai` → `generate-ai-artifacts.md`) — when `generation-ai.json` AND
  `aws-design-ai.json` exist. Writes `ai-migration/`.
- **Billing skeleton** (`artifacts-billing` → `generate-billing-skeleton.md`) — when
  `generation-billing.json` AND `aws-design-billing.json` exist. Writes
  `terraform/skeleton.tf`.

## Step 2: Assemble (docs, report, completion)

Load `references/phases/generate/generate-assemble.md` (the phase's assembler) and
follow it. It reads all generated artifacts to derive `MIGRATION_GUIDE.md`,
`README.md`, and the optional `migration-report.html`, then owns the completion gate.

## Summary

**Use structured completion reporting.** Present final summary to user:

```
Phase 6 (Generate) complete.

✓ Produced:
  - terraform/: [N] files (list key files)
  - scripts/: [N] files
  - ai-migration/: [N] files (if AI route)
  - MIGRATION_GUIDE.md: [N] sections
  - README.md: artifact catalog + quick start
  - migration-report.html: executive summary

⊘ Skipped (not applicable):
  - [artifact]: [reason]

⚠ Skipped (non-blocking failure):
  - migration-report.html: [failure reason]  ← only if report generation failed
```

After the structured block, include:

1. **Artifacts generated** — List all directories and files created (terraform/,
   scripts/, ai-migration/, MIGRATION_GUIDE.md, README.md). Include
   `migration-report.html` only if it exists.
2. **Validation status** — If `$MIGRATION_DIR/validation-report.json` exists, report
   its `status` field (`passed`, `passed_degraded_offline`, or
   `skipped_user_continue`). If `status == "passed_degraded_offline"`, add: "Provider
   registry was unreachable; `terraform validate` was skipped. Re-run `terraform init
   && terraform validate` from a network-connected shell to complete validation."
3. **Key timelines / risks** — Highlight from the generation plans.
4. **TODO markers** — Note any TODO markers in generated artifacts that require manual
   attention.
5. **Next steps** — Recommend reviewing artifacts, customizing TODO sections, and
   beginning migration execution.

Output to user:

- If `migration-report.html` exists: "Migration artifact generation complete. All
  phases of the GCP-to-AWS migration analysis are complete. Your migration report is
  ready at $MIGRATION_DIR/migration-report.html"
- If `migration-report.html` is missing: "Migration artifact generation complete. All
  phases of the GCP-to-AWS migration analysis are complete. Markdown documentation is
  available at $MIGRATION_DIR/MIGRATION_GUIDE.md and $MIGRATION_DIR/README.md. (HTML
  report generation is optional and non-blocking.)"

## Scope Boundary

**This phase covers artifact generation ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Re-designing or changing AWS service selections (Phase 3 decisions are final)
- Re-estimating costs (Phase 4 estimates are final)
- Re-planning the migration (Phase 5 plan is final)
- Asking the user additional clarification questions (Phase 2 is done)
- Discovering new GCP resources (Phase 1 is done)

**Your ONLY job: Transform the plan into deployable artifacts. Nothing else.**
