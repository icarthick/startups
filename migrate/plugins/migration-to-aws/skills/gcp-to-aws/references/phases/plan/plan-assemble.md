---
_assemble: assemble-plan
_of_phase: plan
_reads:
  - plan-infra (fragment contribution)
  - plan-ai (fragment contribution)
  - plan-billing (fragment contribution)
---

# Plan — Assemble & Validate

> **Assembler unit.** The three plan routes (`plan-infra.md`, `plan-ai.md`,
> `plan-billing.md`) each write their own plan artifact directly
> (`generation-infra.json`, `generation-ai.json`, `generation-billing.json`). This
> assembler creates no new file; it is the terminal **validation** unit that owns the
> phase's artifact-level contract — the route output gates. See `plan.md` for how this
> unit is composed into the phase.

**Execute ALL steps in order. Do not skip or deviate.** **Re-read each active route
artifact from disk** before checking — do not trust chat memory.

## Step 1: Determine which routes were active

- **Infra route:** `estimation-infra.json` exists.
- **Billing-only route:** `estimation-billing.json` exists AND `estimation-infra.json` does NOT exist.
- **AI route:** `estimation-ai.json` exists.

## Step 2: Route output gates (fail closed)

1. **At least one route must be active.** If none active → gate failure; the phase must
   not complete.
2. **Each active route produced its expected plan:**
   - Infra route → `generation-infra.json`
   - Billing-only route → `generation-billing.json`
   - AI route → `generation-ai.json`
3. **Mutual exclusion:** `generation-infra.json` and `generation-billing.json` must not
   both exist from the same run.
4. If any active route is missing its expected plan, the completion gate fails.
   Surface: "Plan route [name] did not produce required artifact(s). Re-run the failed
   sub-plan before completing Phase 5." Do **NOT** modify artifacts to force a pass.

## Step 3: Artifact-level contract

The phase's `_postconditions` assert the per-plan shape: `generation-infra.json` (when
present) carries a populated migration timeline, ordering, and risks — the plan is
complete enough for the downstream `generate` phase to build artifacts from it.

On all-pass the interpreter emits `HANDOFF_OK | phase=plan | artifacts=<active plan
files>` and advances to `generate`. On any failure it emits `GATE_FAIL` and stops
without advancing (`INTERPRETER.md` § Gate protocol).
