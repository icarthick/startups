---
_assemble: assemble-design
_of_phase: design
_reads:
  - design-infra (fragment contribution)
  - design-billing (fragment contribution)
  - design-ai (fragment contribution)
---

# Design — Assemble & Validate

> **Assembler unit.** The three design routes (`design-infra.md`, `design-billing.md`,
> `design-ai.md`) each write their own artifact directly (`aws-design.json`,
> `aws-design-billing.json`, `aws-design-ai.json`). This assembler creates no new
> file; it is the terminal **validation** unit that owns the phase's artifact-level
> contract — the route output gates. See `design.md` for how this unit is composed
> into the phase.

**Execute ALL steps in order. Do not skip or deviate.** **Re-read each active route
artifact from disk** before checking — do not trust chat memory.

## Step 1: Determine which routes were active

- **IaC route:** `gcp-resource-inventory.json` AND `gcp-resource-clusters.json` exist.
- **Billing-only route:** `billing-profile.json` exists AND `gcp-resource-inventory.json` does NOT exist.
- **AI route:** `ai-workload-profile.json` exists.

## Step 2: Route output gates (fail closed)

1. **At least one route must be active.** If none active → this is a gate failure; the
   phase must not complete.
2. **Each active route produced its expected artifact:**
   - IaC route → `aws-design.json`
   - Billing-only route → `aws-design-billing.json`
   - AI route → `aws-design-ai.json`
3. **Mutual exclusion:** `aws-design.json` and `aws-design-billing.json` must not both
   exist from the same run (billing-only is the fallback when no IaC exists).
4. If any active route is missing its expected artifact, the completion gate fails.
   Surface: "Design route [name] did not produce required artifact(s). Re-run the
   failed sub-design before completing Phase 3." Do **NOT** modify artifacts to force a
   pass.

## Step 3: Artifact-level contract

The phase's `_postconditions` (in `design.md`) assert the per-artifact shape for each
active route:

- `aws-design.json`: `phase == "design"`, valid timestamp, `services[]` present
  (empty only if all resources deferred), every entry has `service_id`,
  `source_resource_id`, `aws_service`, `confidence`, `aws_config`, and
  `metadata.total_services` matches `services[].length`.
- BigQuery resources (if flagged in discovery) appear as **`Deferred — specialist
  engagement`** — no Athena/Redshift/Glue/EMR recommendation.

On all-pass the interpreter emits `HANDOFF_OK | phase=design | artifacts=<active
design files>` and advances to `estimate` (`INTERPRETER.md` § Gate protocol). On any
failure it emits `GATE_FAIL` and stops without advancing.
