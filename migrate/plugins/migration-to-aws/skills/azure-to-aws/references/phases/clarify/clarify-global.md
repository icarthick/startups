---
_fragment: global
_of_phase: clarify
_contributes:
  - preferences.json (global section; created here, finalized by the assembler)
---

# Clarify — Global Preferences

> **Fragment unit.** See `clarify.md` for how it is composed into the phase.

Gathers the estate-wide answers every Azure migration needs regardless of what the
inventory contains: target AWS region (mapped from the estate's Azure regions rather
than assumed), migration window, environment scope (which of the discovered
subscriptions and environments are in scope), CPU architecture, and cost-optimization
appetite.

**The architecture default is `x86_64`, and that is a deliberate divergence from the
rest of this repo.** Graviton is the default in the GCP and Heroku skills. Azure
fleets carry Windows and .NET routinely, which is exactly the escape path in
`references/shared/graviton.md`, so defaulting to Graviton here would produce a
recommendation that has to be walked back on a large fraction of real estates.
Graviton is offered as an optimization with its own savings line.

## Status — skeleton (build step 1)

Wiring only; the question set and its defaults land in step 5.

## Step: Ask

1. Present the global section of the assumption sheet, batching to at most five
   rows at a time, each with its disposition and default.
2. Accept "use the defaults for the rest" at any point and record the documented
   defaults for the remainder — the phase completes either way.
3. Write the `global` section of `preferences.json`.
