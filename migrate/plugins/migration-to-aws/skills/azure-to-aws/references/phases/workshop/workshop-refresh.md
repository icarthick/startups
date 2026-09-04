---
_fragment: refresh
_of_phase: workshop
---

# Workshop — Apply and Reprice

> **Fragment unit.** See `workshop.md` for how it is composed into the sidebar.

Patches the changed preferences, re-runs Design and Estimate against them, and
snapshots the result under `scenarios/`. Discover is never re-run — the inventory is
unchanged, and re-discovering would make the comparison meaningless as well as slow.

Region dollar deltas need the awspricing MCP. Without it, rates stay
cached-file-based and the scenario is labelled accordingly rather than presented as
precise.

## Status — skeleton (build step 1)

Wiring only; the reprice mechanics land in step 6.
