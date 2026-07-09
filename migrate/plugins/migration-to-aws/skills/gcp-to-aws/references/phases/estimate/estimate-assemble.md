---
_assemble: assemble-estimate
_of_phase: estimate
_reads:
  - estimate-infra (fragment contribution)
  - estimate-billing (fragment contribution)
  - estimate-ai (fragment contribution)
---

# Estimate — Assemble & Validate

> **Assembler unit.** The three estimate routes (`estimate-infra.md`,
> `estimate-billing.md`, `estimate-ai.md`) each write their own artifact directly
> (`estimation-infra.json`, `estimation-billing.json`, `estimation-ai.json`). This
> assembler creates no new file; it is the terminal **validation** unit that owns the
> phase's artifact-level contract — the route output gates. See `estimate.md` for how
> this unit is composed into the phase.

**Execute ALL steps in order. Do not skip or deviate.** **Re-read each active route
artifact from disk** before checking — do not trust chat memory.

## Step 1: Determine which routes were active

- **Infra route:** `aws-design.json` exists.
- **Billing-only route:** `aws-design-billing.json` exists AND `aws-design.json` does NOT exist.
- **AI route:** `aws-design-ai.json` exists.

## Step 2: Route output gates (fail closed)

1. **At least one route must be active.** If none active → gate failure; the phase must
   not complete.
2. **Each active route produced its expected artifact:**
   - Infra route → `estimation-infra.json`
   - Billing-only route → `estimation-billing.json`
   - AI route → `estimation-ai.json`
3. **Mutual exclusion:** `estimation-infra.json` and `estimation-billing.json` must not
   both exist from the same run.
4. If any active route is missing its expected artifact, the completion gate fails.
   Surface: "Estimate route [name] did not produce required artifact(s). Re-run the
   failed sub-estimate before completing Phase 4." Do **NOT** modify artifacts to force
   a pass.

## Step 3: Infra route additional checks (when `estimation-infra.json` exists)

- `recommendation.path` ∈ `{migrate_optimized, migrate_phased, stay}`
- `recommendation.path_label` is non-empty
- `recommendation.migrate_if` and `recommendation.stay_if` are non-empty arrays

If these fail, surface: "Re-run `estimate-infra.md` Part 7 (recommendation block)."

## Step 4: Pricing-source contract

Every priced service carries a `pricing_source` in `{cached, live, cached_fallback,
unavailable}`. Services with `pricing_source: unavailable` are listed in
`services_with_missing_fallback` and excluded from totals (they are not silently
dropped). This is asserted in the phase's `_postconditions`.

On all-pass the interpreter emits `HANDOFF_OK | phase=estimate | artifacts=<active
estimate files>` and advances to `generate`. On any failure it emits `GATE_FAIL` and
stops without advancing (`INTERPRETER.md` § Gate protocol).
