---
_fragment: sheet
_of_phase: workshop
---

# Workshop — Assumption Sheet

> **Fragment unit.** See `workshop.md` for how it is composed into the sidebar.

Presents the current assumptions as an editable sheet and collects the user's
changes. It writes no artifact of its own — the scenario snapshot is the refresh
fragment's job, and the index is the assembler's — which is why it declares no
`_contributes`.

Knobs: region, HA posture, compute target, cost-optimization appetite, CPU
architecture. Each row shows the current value and where it came from (a Clarify
answer, a detected fact, or a skill default), so the user can see what they are
overriding.

## Status — skeleton (build step 1)

Wiring only; the knob set and its presentation land in step 6.
