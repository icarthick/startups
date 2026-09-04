---
_fragment: artifacts-docs
_of_phase: generate
_contributes:
  - MIGRATION_GUIDE.md
  - README.md
---

# Generate — Documentation

> **Fragment unit.** See `generate.md` for how it is composed into the phase.

`MIGRATION_GUIDE.md` is the runbook: prerequisites, the cutover sequence in tier
order, and a Verification section per migrated service. `README.md` lists what was
generated and how to apply it.

Where a specialist gate deferred a resource, the guide says so plainly and names what
a specialist would need to decide. A deferral that does not surface in the runbook is
a deferral the customer discovers during cutover.

## Status — skeleton (build step 1)

Wiring only; the doc emitters land in step 6.
