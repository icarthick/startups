---
_assemble: assemble-generate
_of_phase: generate
_reads:
  - artifacts-infra (fragment contribution)
  - artifacts-scripts (fragment contribution)
  - artifacts-ai (fragment contribution)
  - artifacts-billing (fragment contribution)
_produces:
  - MIGRATION_GUIDE.md
  - README.md
  - { file: migration-report.html, _when: "artifact validation passed (optional, non-blocking)" }
---

# Generate — Docs, Report & Completion (Assembler)

> **Assembler unit.** The generate fragments (`generate-terraform.md`,
> `generate-scripts.md`, `generate-ai-artifacts.md`, `generate-billing-skeleton.md`)
> each wrote their own artifact tree (`terraform/`, `scripts/`, `ai-migration/`,
> `terraform/skeleton.tf`, `validation-report.json`). This assembler is the **single
> creator** of the cross-cutting artifacts that must read ALL of those siblings:
> `MIGRATION_GUIDE.md`, `README.md`, and the optional `migration-report.html`. That
> read-all-siblings dependency is exactly why they are assembler-owned and not
> fragments (`INTERPRETER.md` § the unit kinds). See `generate.md` for how this unit is
> composed into the phase.

**Execute ALL steps in order. Do not skip or optimize.** **Re-read the generated
artifacts from disk** before deriving docs/report.

## Step 1: Documentation (always)

Load `references/generate/generate-docs.md` → writes `MIGRATION_GUIDE.md` and
`README.md`. It scans all generated artifacts (`terraform/`, `scripts/`,
`ai-migration/`) to build the catalog + guide.

## Step 2: HTML Report (always runs last, optional output)

1. Run `shared/validate-artifacts.md` first (read-only validation across the generated
   artifacts; for the infra route this confirms `validation-report.json`).
2. Load `references/generate/generate-report.md` → writes `migration-report.html`.

**Validation gate:** if validation emits `GATE_FAIL`, log the failure to the user, **do
not write** `migration-report.html`, and continue to completion — the report is
optional and non-blocking, but a validation failure is never a silent skip. Do **NOT**
patch artifacts to pass validation.

## Step 3: Completion gate (fail closed)

Verify (the phase's `_postconditions` assert these):

1. **Artifact route gates:**
   - infra artifact route active (`generation-infra.json` AND `aws-design.json`) →
     `terraform/`, `scripts/`, and `validation-report.json` (`status` ∈ `{passed,
     passed_degraded_offline, skipped_user_continue}`) exist;
   - AI artifact route active (`generation-ai.json` AND `aws-design-ai.json`) →
     `ai-migration/` exists;
   - billing artifact route active (`generation-billing.json` AND
     `aws-design-billing.json`) → `terraform/skeleton.tf` exists.
2. **Documentation gate (always):** `MIGRATION_GUIDE.md` and `README.md` exist.
3. **No placeholder tokens** remain unresolved in generated `.tf` files.

If any active route is missing expected outputs, the interpreter emits `GATE_FAIL |
phase=generate | field=<artifact> | reason=missing` and stops — do **NOT** modify
artifacts to force a pass. On all-pass it emits `HANDOFF_OK | phase=generate` and
advances to `complete` (`INTERPRETER.md` § Gate protocol).
