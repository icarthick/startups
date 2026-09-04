---
_assemble: assemble-workshop
_of_phase: workshop
_reads:
  - sheet
  - refresh
  - compare
_produces:
  - scenarios/index.json
---

# Workshop — Resolve the Sidebar

> **Assembler unit.** The single creator of `scenarios/index.json`. See
> `workshop.md` for how it is composed into the sidebar.

Writes the scenario index, marks `phases.workshop` as `"completed"`, and returns
control so the post-Estimate gate can be re-presented. Resolving includes the
decline path: a user who enters and leaves without repricing still resolves the
sidebar, which lifts the `_gates: generate` hold.

`scenarios/index.json`'s contract is in
`references/shared/schema-workshop-scenarios.md`.

## Status — skeleton (build step 1)

Wiring only; the index shape and the return-to-gate handoff land in step 6.
