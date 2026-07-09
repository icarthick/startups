---
_assemble: assemble-generate
_of_phase: generate
_reads:
  - plan-infra (fragment contribution)
  - plan-ai (fragment contribution)
  - plan-billing (fragment contribution)
_produces:
  - { file: terraform/, _when: "infra artifact route active (generation-infra.json AND aws-design.json exist)" }
  - { file: scripts/, _when: "infra artifact route active (generation-infra.json AND aws-design.json exist)" }
  - { file: validation-report.json, _when: "infra artifact route active" }
  - { file: ai-migration/, _when: "AI artifact route active (generation-ai.json AND aws-design-ai.json exist)" }
  - { file: terraform/skeleton.tf, _when: "billing artifact route active (generation-billing.json AND aws-design-billing.json exist)" }
  - MIGRATION_GUIDE.md
  - README.md
  - { file: migration-report.html, _when: "artifact validation passed (optional, non-blocking)" }
---

# Generate — Stage 2 Artifacts + Completion (Assembler)

> **Assembler unit.** The Stage 1 `plan-*` fragments each wrote their execution plan
> (`generation-infra.json`, `generation-ai.json`, `generation-billing.json`). This
> assembler is the **single creator** of every Stage 2 artifact: it reads those plans
> plus the design artifacts and derives the deployable output. It is the only unit
> allowed to read fragment output, which is why the Stage 1 → Stage 2 dependency lives
> here rather than in a second set of fragments (`INTERPRETER.md` § the unit kinds).
> See `generate.md` for how this unit is composed into the phase.

**Execute ALL steps in order. Do not skip or optimize.** Proceed only after Stage 1
plans exist. **Re-read plans + designs from disk** before generating.

## Dirty-state tracking (resumability)

Before Stage 2 outputs, update `dirty_state` in `.phase-status.json` so an interrupted
run can resume:

```json
"dirty_state": {
  "phase": "generate",
  "stage": "stage_2_artifacts",
  "started_at": "<ISO 8601 UTC>",
  "partial_outputs": ["generation-infra.json"],
  "missing_outputs": ["terraform/", "scripts/", "MIGRATION_GUIDE.md", "README.md"]
}
```

Trim `missing_outputs` to the artifacts expected for the active routes plus the
mandatory docs. Update `partial_outputs`/`missing_outputs` after each sub-file
completes.

## Step 1: Infrastructure Artifacts

IF `generation-infra.json` AND `aws-design.json` exist:

1. Load `generate-artifacts-infra.md` → writes the `terraform/` directory.
2. Then load `generate-artifacts-scripts.md` → writes the `scripts/` directory.

## Step 2: AI Artifacts

IF `generation-ai.json` AND `aws-design-ai.json` exist:

> Load `generate-artifacts-ai.md` → writes the `ai-migration/` directory.

## Step 3: Billing Skeleton Artifacts

IF `generation-billing.json` AND `aws-design-billing.json` exist:

> Load `generate-artifacts-billing.md` → writes `terraform/skeleton.tf` (with TODO
> markers).

## Step 4: Documentation (always)

AFTER all active artifact sub-files complete:

> Load `generate-artifacts-docs.md` → writes `MIGRATION_GUIDE.md` and `README.md`.

## Step 5: HTML Report (always runs last, optional output)

AFTER documentation:

1. Run `shared/validate-artifacts.md` first (this writes/verifies
   `validation-report.json` for the infra route).
2. Load `generate-artifacts-report.md` → writes `migration-report.html`.

**Validation gate:** if validation emits `GATE_FAIL`, log the failure to the user, **do
not write** `migration-report.html`, and continue to completion — the report is
optional and non-blocking, but a validation failure is never a silent skip. Do **NOT**
patch artifacts to pass validation.

## Step 6: Completion gate (fail closed)

Verify both stages (the phase's `_postconditions` assert these):

1. **Stage 1 route gates:** for each estimation artifact present, the matching plan
   exists (`estimation-infra.json`→`generation-infra.json`, etc.).
2. **Stage 2 route gates:**
   - infra artifact route active → `terraform/`, `scripts/`, and
     `validation-report.json` (`status` ∈ `{passed, passed_degraded_offline,
     skipped_user_continue}`) exist;
   - AI artifact route active → `ai-migration/` exists;
   - billing artifact route active → `terraform/skeleton.tf` exists.
3. **Documentation gate (always):** `MIGRATION_GUIDE.md` and `README.md` exist.

If any active route is missing expected outputs, the interpreter emits `GATE_FAIL |
phase=generate | field=<artifact> | reason=missing` and stops — do **NOT** modify
artifacts to force a pass. On all-pass it emits `HANDOFF_OK | phase=generate` and
advances to `complete` (`INTERPRETER.md` § Gate protocol).
