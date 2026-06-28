---
# ============================================================================
# estimate.phase.md — Phase 4 (Estimate).
# THIN phase: frontmatter = contract; body = one ## Orientation + (this phase has
# zero steps of its own — work is the fragment + assembler).
#
# Estimate is the genuinely MATH-HEAVY phase (chained per-service cost formulas,
# Property-16 summation, tier scaling, annualization). The arithmetic-probe
# (test-output/estimate-arithmetic-probe.md) confirmed the chained arithmetic
# reproduces deterministically from prose + a rates JSON, AND caught the
# multi-AZ convention hazard (RDS baked-in vs ElastiCache x2 vs Aurora
# intrinsic) — now encoded per-service in knowledge/estimate/aws-pricing.json.
#
# Single responsibility (compute the financial picture) -> ONE cost-engine
# fragment + one validator assembler (owns the Property-16 total invariant +
# every-service-priced + recommendation/complexity gates).
#
# EKS-aware: the cost engine handles an eks_cluster design entry (pods $0 +
# post-loop control-plane + node cost) even though design's EKS branch is a stub,
# so estimate needs no retrofit when EKS lands.
# ============================================================================
_phase: estimate
_title: "Estimate AWS Costs"
_requires_phase: design
_scope: >
  Compute the financial picture of the designed migration: per-service monthly
  AWS cost, observability, three pricing tiers, Heroku-vs-AWS comparison, ROI,
  complexity tier, optimization opportunities, and a recommendation. ONLY this.
  No changes to the design mappings, no Terraform/IaC, no migration runbooks, no
  human/labor cost, no AI-workload estimation.

_input:
  - aws-design.json
  - preferences.json
  - heroku-resource-inventory.json

_knowledge:
  - { file: knowledge/estimate/aws-pricing.json }
  - { file: knowledge/estimate/estimate-defaults.json }

_re_entry_guard:
  if: "generation-warnings.json exists OR a terraform/ directory exists, AND phase generate completed"
  action: _halt_and_inform
  reason: stale_downstream
  on_confirm: >
    Reset phases generate, feedback to "pending" in .phase-status.json (leave
    estimate as the active in_progress phase), and remove their downstream
    artifacts from $MIGRATION_DIR/ if present: generation-warnings.json, the
    terraform/, kubernetes/ and scripts/ directories, MIGRATION_GUIDE.md,
    README.md, and feedback.json. estimation-infra.json itself is NOT removed —
    the re-run overwrites it. Then run estimate normally. NEVER perform this
    reset without the user's explicit confirmation.

_preconditions:
  - _check_single_active_phase: true
    _on_failure:
      _halt_and_inform: >
        Another core phase is already in_progress. Resolve it before re-running
        estimate.
  - _check_phase_completed: design
    _on_failure:
      _halt_and_inform: >
        Design has not completed. Run Phase 3 (design.phase.md) first — estimate
        reads aws-design.json.
  - _check_file_exists: [aws-design.json, preferences.json, heroku-resource-inventory.json]
    _on_failure:
      _unrecoverable: >
        A required input is missing (aws-design.json / preferences.json /
        heroku-resource-inventory.json). All three are required.
  - _validate_json: [aws-design.json, preferences.json]
    _on_failure:
      _unrecoverable: >
        An input file does not parse as valid JSON. Re-run the producing phase.
  - _check_source_exists: { glob: "aws-design.json", containing: '"services"' }
    _on_failure:
      _unrecoverable: >
        aws-design.json has no services[]. Re-run design.

_fragments:
  - _id: cost-engine
    _trigger: { _always: true }
    _file: phases/estimate/estimate-cost-engine.md

_assemble:
  _file: phases/estimate/estimate-assemble.md

_postconditions:
  - _check_file_exists: estimation-infra.json
  - _assert: "estimation-infra.json has phase == 'estimate'"

_produces: [estimation-infra.json]
_advances_to: generate
_forbids_files:
  - README.md
  - estimate-summary.md
  - "*.txt"
  - "terraform/**"
  - MIGRATION_GUIDE.md

_on_error:
  _warn_and_skip:    { effect: "record warning; skip this item; continue",            status: continue }
  _default_and_warn: { effect: "apply documented default; record warning; continue",   status: continue }
  _halt_and_inform:  { effect: "stop; surface diagnostic",                             status: retain_in_progress }
  _unrecoverable:    { effect: "stop; surface error",                                  status: revert_to_pending }
---

# Estimate AWS Costs

## Orientation

Compute the full financial picture for the designed migration and write a single
`estimation-infra.json` in `$MIGRATION_DIR/`, consumed by Generate (for the
guide) and presented to the user. The work is ONE FRAGMENT + one ASSEMBLER:

1. **cost-engine** fragment (`phases/estimate/estimate-cost-engine.md`) — the
   single unit of work: select the pricing source, compute per-service costs
   (applying each service's multi-AZ convention from `aws-pricing.json`), add the
   post-loop NAT + observability + EKS-cluster costs, sum to the balanced total
   (Property-16), derive premium/optimized tiers + annual figures, compare to the
   Heroku baseline, classify complexity, list optimization opportunities, and
   form a recommendation. CREATES `estimation-infra.json`.
2. **estimate-assemble** (`phases/estimate/estimate-assemble.md`) — validator
   assembler owning the artifact contract: schema, the Property-16 total ==
   sum-of-lines invariant, every-design-service-priced (or warned), and the
   recommendation/complexity gates.

The cost arithmetic is data-driven: rates + per-service formulas + the multi-AZ
convention are in `knowledge/estimate/aws-pricing.json`; tier scaling,
observability heuristics, complexity thresholds, the optimization catalog, and
recommendation logic are in `knowledge/estimate/estimate-defaults.json`. The
output SHAPE is `schemas/estimation-infra.schema.json`. After the assembler
validates, the phase emits `HANDOFF_OK | phase=estimate | ...`, sets
`phases.estimate="completed"`, `current_phase="generate"`, and tells the user to
load `generate.phase.md` next.
