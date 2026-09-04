---
_fragment: infra
_of_phase: estimate
_contributes:
  - estimation-infra.json
---

# Estimate — Infrastructure Cost Engine

> **Fragment unit.** See `estimate.md` for how it is composed into the phase.

Prices every service in `aws-design.json` and derives the Azure baseline it is
compared against.

## Two totals, always

- **Non-optimized (1:1 lift)** — price each mapped service at the size the Azure
  resource is running today. No right-sizing, no architecture change.
- **Right-sized** — price the design as recommended, including measured right-sizing
  and the CPU-architecture choice.

Report both, plus `cost_comparison` stating the delta and
`optimization_opportunities` itemizing where the delta came from.

## Baseline derivation, highest confidence first

1. An Azure Cost Management export, when the customer supplied one.
2. RDfA consumption data — with reserved resources priced at their RI-equivalent
   rate, never at the literal `$0` that consumption reports.
3. Derived from discovered SKUs against cached Azure rates.

Label the baseline with the rung that produced it. A baseline derived from SKUs is
not a bill and must not be presented as one.

## Status — skeleton (build step 1)

Wiring only. The pricing formulas, the dual-output arithmetic, and the licensing
delta line land in steps 5–6.
