---
# ============================================================================
# design.phase.md — Phase 3 (Design).
# THIN phase: frontmatter = phase-level contract; the BODY is composed of
# FRAGMENTS + one ASSEMBLER (the unit taxonomy — see ../INTERPRETER.md).
#
# Design is a SINGLE-RESPONSIBILITY phase: one deterministic single-pass mapping
# of every inventory resource to its AWS equivalent (flat, input order, no
# clustering), PLUS the VPC/security-group design and Fir notation that derive
# from that same pass. One source (inventory + preferences), one reason to
# change -> ONE fragment (mapping-engine). The assembler validates aws-design.json
# and enforces the route output gates (its postconditions ARE the handoff gate).
#
# The mapping engine is the DSL thesis's first MATH-bearing phase. The
# arithmetic-probe (test-output/design-arithmetic-probe.md) showed the numeric
# work is table LOOKUP + a 0-100 clamp + tier branches, all reproducible by a
# cold LLM PROVIDED the source figures are demoted to provenance so nothing
# invites re-derivation. The knowledge JSONs in knowledge/design/ carry that
# "do not recompute" guard. Deterministic leaves stay in DATA; the fragment only
# does the lookup/clamp/branch the data dictates.
#
# EKS: clarify's design_constraints.kubernetes defaults to ecs-fargate. This phase
# authors BOTH compute paths: Fargate (mapping-engine) and EKS (eks-mapping, the
# all-or-nothing alternative gated on an eks-* preference). EKS formations -> pods
# + a single eks_cluster aggregate sized from all formations; the assembler merges
# the EKS design in. Estimate prices pods at $0 + the cluster post-loop; generate
# emits eks.tf + kubernetes/ manifests.
# ============================================================================
_phase: design
_title: "Design AWS Architecture"
_requires_phase: clarify
_scope: >
  Map each Heroku resource to its AWS equivalent via deterministic lookup tables
  (flat list, input order), design the VPC + security groups, and note Fir
  workloads as deferred. ONLY this. No cost/pricing (that is estimate), no
  Terraform/HCL (that is generate), no migration scripts, no clarify questions,
  no discovery. Mapping ONLY.

_input:
  - heroku-resource-inventory.json
  - preferences.json

_knowledge:
  - { file: knowledge/design/design-defaults.json }
  - { file: knowledge/design/dyno-fargate-sizing.json,      _when: "inventory has a formation AND design_constraints.kubernetes.value is ecs-fargate or absent" }
  - { file: knowledge/design/eks-pod-sizing.json,           _when: "inventory has a formation AND design_constraints.kubernetes.value is eks-managed or eks-or-ecs" }
  - { file: knowledge/design/postgres-rds-sizing.json,      _when: "inventory has a heroku-postgresql addon" }
  - { file: knowledge/design/redis-elasticache-sizing.json, _when: "inventory has a heroku-redis addon" }
  - { file: knowledge/design/kafka-msk-sizing.json,         _when: "inventory has a heroku-kafka addon" }
  - { file: knowledge/design/fast-path-addons.json,         _when: "inventory has a non-core addon (not postgresql/redis/kafka)" }

_re_entry_guard:
  if: "estimation-infra.json exists AND phase estimate completed"
  action: _halt_and_inform
  reason: stale_downstream
  on_confirm: >
    Reset phases estimate, generate, feedback to "pending" in .phase-status.json
    (leave design as the active in_progress phase), and remove their downstream
    artifacts from $MIGRATION_DIR/ if present: estimation-infra.json,
    generation-warnings.json, the terraform/, kubernetes/ and scripts/
    directories, MIGRATION_GUIDE.md, README.md, and feedback.json. aws-design.json
    itself is NOT removed — the re-run overwrites it. Then run design normally.
    NEVER perform this reset without the user's explicit confirmation.

_preconditions:
  - _check_single_active_phase: true
    _on_failure:
      _halt_and_inform: >
        Another core phase is already in_progress. At most one phase may be
        active at a time. Resolve the active phase before re-running design.
  - _check_phase_completed: clarify
    _on_failure:
      _halt_and_inform: >
        Clarify has not completed. Run Phase 2 (clarify.phase.md) first — design
        reads preferences.json.
  - _check_file_exists: [heroku-resource-inventory.json, preferences.json]
    _on_failure:
      _unrecoverable: >
        A required input (heroku-resource-inventory.json or preferences.json) is
        missing. Both are required to map resources.
  - _validate_json: [heroku-resource-inventory.json, preferences.json]
    _on_failure:
      _unrecoverable: >
        An input file does not parse as valid JSON. Re-run the producing phase.

# Phase body: TWO fragments + one assembler (the discover-style merge shape).
#   - mapping-engine [always]: non-formation services + VPC + Fir + Fargate
#     formations (when NOT eks); CREATES aws-design.json.
#   - eks-mapping [eks pref only]: formations -> EKS pods + the eks_cluster
#     aggregate; CREATES _eks-design.json (its own artifact).
# The assembler MERGES _eks-design.json into aws-design.json (one creator per
# artifact; assembler-only mutation). All-or-nothing: EKS replaces Fargate for
# ALL formations when selected.
_fragments:
  - _id: mapping-engine
    _trigger: { _always: true }
    _file: phases/design/design-mapping.md
  - _id: eks-mapping
    _trigger: { _when: "preferences.design_constraints.kubernetes.value is 'eks-managed' or 'eks-or-ecs'" }
    _file: phases/design/design-eks.md

_assemble:
  _file: phases/design/design-assemble.md

_postconditions:
  - _check_file_exists: aws-design.json
  - _assert: "aws-design.json has phase == 'design'"

_produces: [aws-design.json]
_advances_to: estimate
_forbids_files:
  - README.md
  - design-summary.md
  - "*.txt"
  - estimation-infra.json
  - MIGRATION_GUIDE.md
  - "terraform/**"

_on_error:
  _warn_and_skip:    { effect: "record warning; skip this resource; continue",          status: continue }
  _defer:            { effect: "append a deferred[] entry; continue",                    status: continue }
  _default_and_warn: { effect: "apply documented default; record warning; continue",     status: continue }
  _halt_and_inform:  { effect: "stop; surface diagnostic",                               status: retain_in_progress }
  _unrecoverable:    { effect: "stop; surface error",                                    status: revert_to_pending }
---

# Design AWS Architecture

## Orientation

Map every resource in `heroku-resource-inventory.json` to its AWS equivalent
using the deterministic lookup tables in `knowledge/design/`, design the VPC +
security groups, and note Fir workloads as deferred — assembling a single
`aws-design.json` in `$MIGRATION_DIR/`. The output is consumed by Estimate and
Generate. No clustering; resources are a flat list processed in input order.

The work is composed of TWO FRAGMENTS + one ASSEMBLER (the unit taxonomy — see
`../INTERPRETER.md`; this is the discover-style merge shape):

1. **mapping-engine** fragment (`phases/design/design-mapping.md`) — always-on.
   Single-pass maps each resource (formation → Fargate WHEN NOT EKS, postgres →
   RDS/Aurora, redis → ElastiCache, kafka → MSK, other addons → fast-path,
   pipeline → detect-only warning, space → collected for VPC), designs the VPC +
   security groups, notes Fir. CREATES `aws-design.json`.
2. **eks-mapping** fragment (`phases/design/design-eks.md`) — fires only on an
   `eks-managed`/`eks-or-ecs` preference. Maps every formation to an EKS
   Deployment pod entry + the single `eks_cluster` aggregate (sized from all
   formations). CREATES its own `_eks-design.json` (intermediate).
3. **design-assemble** (`phases/design/design-assemble.md`) — the mandatory
   assembler. MERGES `_eks-design.json` into `aws-design.json` when present
   (folds in the EKS services + the `eks_cluster` key), then owns the
   artifact-level contract (schema-shape + route output gates). One creator per
   artifact; the assembler is the only mutator.

EKS is ALL-OR-NOTHING: when selected, EVERY formation maps to EKS (not Fargate),
decided by the `kubernetes.value` preference. The default (`ecs-fargate` /
absent) path runs the Fargate formation branch in mapping-engine and the
eks-mapping fragment never fires.

Run the fragment(s) in `_fragments` order (skipping false triggers), then the
assembler. Each is a first-class DSL unit with its OWN frontmatter — read each
file for its contract; this phase only composes them and owns lifecycle +
cross-cutting checks.

After the assembler validates the artifact, the phase `_postconditions` run; on
full pass the interpreter emits `HANDOFF_OK | phase=design | ...`, sets
`phases.design="completed"`, `current_phase="estimate"`, and tells the user to
load `estimate.phase.md` next.
