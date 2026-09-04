---
_assemble: assemble-preferences
_of_phase: clarify
_reads:
  - global (fragment contribution)
_produces:
  - preferences.json
_knowledge:
  - { file: references/shared/schema-preferences.md }
---

# Clarify — Assemble Preferences

> **Assembler unit.** The single creator of `preferences.json` and the owner of its
> final contract. See `clarify.md` for how it is composed into the phase.

**Schema reference**: `references/shared/schema-preferences.md`.

## Assembly rules

1. Merge every fragment's sheet section into one `preferences.json`.
2. Every row carries `disposition` (DETECTED / PROPOSED / ESSENTIAL / N/A), `value`,
   and `default`. A row the user never answered keeps its documented default and
   stays PROPOSED — never silently promote a default to a user decision.
3. Record `licensing` as N/A explicitly when the licensing gate did not fire. An
   absent key and a considered N/A are different facts, and the report distinguishes
   them.
4. Carry the user's confirmed or corrected cluster `pattern_id` values forward, so
   Design consumes a validated pattern rather than re-deriving one.

## Validation Checklist

- [ ] `global.target_region` is set.
- [ ] `design_constraints.cpu_architecture` is set, with `x86_64` recorded as the default.
- [ ] `identity` is set (Category J always fires).
- [ ] `licensing` is either answered or explicitly N/A.
- [ ] Every App Service Plan hosting more than one app has an isolation answer, or the recorded default of "no split".
- [ ] Every cluster carrying a `pattern_id` has a user-confirmed value.
- [ ] No secret values were copied out of the inventory into preferences.

## Status — skeleton (build step 1)

Writes the artifact and owns the checklist above. The checklist is already the
finished contract; step 5 adds the per-category sections that satisfy it.
