---
_assemble: assemble-generation
_of_phase: generate
_reads:
  - artifacts-infra (fragment contribution)
  - artifacts-docs (fragment contribution)
  - artifacts-report (fragment contribution)
_produces:
  - generation-warnings.json
---

# Generate — Assemble and Account

> **Assembler unit.** The single creator of `generation-warnings.json`. The
> artifact-emitting fragments create their own files; this unit's job is to prove
> nothing was dropped. See `generate.md` for how it is composed into the phase.

## Assembly rules

1. Walk `aws-design.json` `services[]` and confirm every entry either produced an
   artifact or has a `generation-warnings.json` entry saying why not.
2. Carry every `deferred[]` entry into the warnings file with its reason and the
   recommendation, so a specialist deferral is visible in the output and not only in
   the design.
3. Scan the emitted `.tf` files for leftover `{{VARIABLE}}` placeholders and for any
   secret value from the inventory. Either is a gate failure, not a warning.
4. Emit nothing that overwrites a phase input — the phase's `_forbids_files` names
   the state artifacts explicitly.

## Status — skeleton (build step 1)

Writes the warnings file and owns the accounting contract above. The scan
implementations land in step 6.
