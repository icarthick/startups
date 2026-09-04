---
_fragment: artifacts-report
_of_phase: generate
_contributes:
  - migration-report.html
---

# Generate — Stakeholder Report

> **Fragment unit.** See `generate.md` for how it is composed into the phase.

The customer-facing report. **It leads with the cluster-level architecture
rationale** — what workloads were found, what each becomes, and why — and moves the
per-resource mapping table to an appendix. This is the visible payoff of the holistic
goal and the part a customer actually reads; a 40-row table as the headline buries
the argument.

It also surfaces, rather than hides:

- Drift between declared IaC and running state.
- Reserved-instance baselines, and the fact that a `$0` consumption line was
  substituted with an RI-equivalent rate.
- Any `unclassified` cluster, so the output does not overclaim architectural insight.
- The what-if scenario comparison when at least two scenarios were priced.

Every report carries a draft-for-review footer.

## Status — skeleton (build step 1)

Wiring only; the renderer lands in step 6.
