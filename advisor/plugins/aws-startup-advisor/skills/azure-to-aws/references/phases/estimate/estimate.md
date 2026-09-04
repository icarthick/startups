---
_phase: estimate
_title: "Estimate AWS Costs"
_requires_phase: design
_input:
  - aws-design.json
  - preferences.json
  - azure-resource-inventory.json
_knowledge:
  - { file: references/vendored/pricing/aws-infra-pricing.json }
  - { file: references/vendored/estimate/complexity-tiers.json }
  - { file: references/vendored/estimate/estimation-infra.schema.json }
  - { file: references/vendored/estimate/pricing-mode.md }
_fragments:
  - _id: infra
    _trigger: { _always: true }
    _file: phases/estimate/estimate-infra.md
_assemble:
  _file: phases/estimate/estimate-assemble.md
_produces:
  - estimation-infra.json
_advances_to: generate
_re_entry_guard:
  _stale_if_completed: generate
  _stale_artifact: MIGRATION_GUIDE.md
  _on_reentry: stop_unless_confirmed
  _on_confirm: reset_downstream_to_pending
_preconditions:
  - _check_phase_completed: design
    _on_failure: _halt_and_inform
  - _check_single_active_phase: true
    _on_failure: _halt_and_inform
  - _check_file_exists: [aws-design.json, preferences.json, azure-resource-inventory.json]
    _on_failure: _unrecoverable
  - _validate_json: [aws-design.json, preferences.json, azure-resource-inventory.json]
    _on_failure: _unrecoverable
  - _assert: "aws-design.json services[] exists and is non-empty, and every entry has aws_service and aws_config"
    _on_failure: _unrecoverable
_postconditions:
  - _check_file_exists: estimation-infra.json
    _on_failure: _halt_and_inform
  - _validate_json: estimation-infra.json
    _on_failure: _halt_and_inform
  - _assert: "projected_costs carries BOTH a non-optimized 1:1 lift total and a right-sized total, and cost_comparison states the delta between them"
    _on_failure: _halt_and_inform
  - _assert: "no reserved-instance resource was priced from a literal $0 consumption figure; every such resource used its RI-equivalent rate as the baseline, and the substitution is recorded"
    _on_failure: _halt_and_inform
  - _assert: "recommendation.outcome is one of {go, conditional_go, defer_for_evidence, stay}; conditions is a non-empty array when outcome is conditional_go"
    _on_failure: _halt_and_inform
  - _assert: "every service in aws-design.json services[] appears in the cost breakdown, or is listed as 'unpriced' in warnings"
    _on_failure: _halt_and_inform
  - _assert: "the right-sized total equals the arithmetic sum of its per-service costs, excluding unpriced"
    _on_failure: _halt_and_inform
  - _assert: "complexity_tier is one of {small, medium, large}"
    _on_failure: _halt_and_inform
  - _assert: "if preferences.json records a licensing answer, a single licensing delta line item is present; if licensing is N/A, no licensing line item appears"
    _on_failure: _halt_and_inform
  - _assert: "no human labor, professional services, or people-time appears as a dollar figure or a one-time migration cost category"
    _on_failure: _halt_and_inform
  - _assert: "run_mode is set in .phase-status.json to either 'decide' or 'decide_and_execute' — the decision gate was presented and answered"
    _on_failure: _halt_and_inform
_forbids_files:
  - README.md
  - "*.txt"
  - "terraform/**"
  - MIGRATION_GUIDE.md
---

# Phase 4: Estimate AWS Costs

## Orientation

Price the design, and price it twice.

**Dual output is the default shape, not an option.** A non-optimized 1:1 lift and a
right-sized target are both reported, with the delta between them stated. The 1:1
number is what a naive migration costs and it is what the customer will otherwise
assume; the right-sized number is the recommendation. Showing only one of them either
overstates the bill or hides the work that produced the saving.

`estimation-infra.schema.json` has no `additionalProperties: false` and already
carries `cost_comparison` and `optimization_opportunities`, so this needs no schema
change — which matters, because that schema is vendored into several skills and
drift-allowlisted.

## The reservation `$0` trap

A reserved VM shows up at **`$0`** in consumption data. It is not free: it was
pre-paid. Pricing the Azure baseline from the literal figure understates current
spend, which makes the AWS comparison look worse than it is and can invert the
recommendation. Every reserved resource is priced from its RI-equivalent rate, and
the substitution is recorded so the report can show its work.

## Metrics lookback affects confidence

Read the actual metrics window from the RDfA report metadata rather than assuming 31
days. Below roughly 14 days, downgrade right-sizing confidence — a P95 over a short
window is not a measurement.

## Status — skeleton (build step 1)

Wiring only: one cost-engine fragment, one assembler, and the postconditions that
encode the finished contract. The vendored pricing file, complexity tiers, estimate
schema, and the canonical pricing-mode Step 0 are already wired through `_knowledge`.

| Lands in | What                                                                           |
| -------- | ------------------------------------------------------------------------------ |
| step 5   | `knowledge/estimate/rightsizing-thresholds.json` (P95 bands + the aggressiveness slider) and `estimate-defaults.json` |
| step 6   | The dual output, the licensing delta line item, and the decision gate itself    |
| step 6   | The AI and billing-only estimate routes                                        |

## Step: Run the phase

1. Execute `references/vendored/estimate/pricing-mode.md` as Step 0.
2. Run each fragment whose `_trigger` holds.
3. Run `estimate-assemble.md`, which presents the decision gate and writes `run_mode`.
4. Evaluate `_postconditions`. On all-pass emit `HANDOFF_OK`; on any failure emit
   `GATE_FAIL` and stop.
