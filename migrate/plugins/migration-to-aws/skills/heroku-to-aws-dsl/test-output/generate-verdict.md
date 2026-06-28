# Generate Phase (DSL port) — VERDICT

**Change:** Ported Phase 5 (Generate) from the upstream markdown
(`generate.md` + `generate-terraform.md` + `generate-docs.md`) into the DSL. This
is the MULTI-ARTIFACT phase and the taxonomy's real stress test: it emits a
`terraform/` directory (10 files), `MIGRATION_GUIDE.md`, `README.md`, `scripts/`,
and `generation-warnings.json`.

Files authored (full Fargate path; EKS stubbed):

- `phases/generate.phase.md` — thin phase: requires estimate, TWO fragments
  (terraform | docs) + a cross-artifact validator assembler, EKS-generate stub
  gated on an EKS design entry, advances to feedback.
- `phases/generate/generate-terraform.md` — routing-algorithm fragment: selects
  `templates/generate/terraform/*.tmpl` per `knowledge/generate/generate-routing.json`,
  fills `{{placeholders}}`, writes `terraform/` + `generation-warnings.json`.
- `phases/generate/generate-docs.md` — fills doc + script templates with
  conditional sections; writes `MIGRATION_GUIDE.md`, `README.md`, `scripts/`.
- `phases/generate/generate-assemble.md` — the first NON-TRIVIAL assembler: a
  cross-artifact validator assembler (coverage, README-refs, no-placeholder-leak,
  reference-integrity, required-files) — its postconditions ARE the gate.
- `phases/generate/generate-eks.md` — EKS-generate loud-halt stub (gated).
- `templates/generate/terraform/*.tmpl` (main, variables, outputs, vpc-new,
  vpc-existing, security-restricted, security-standard, compute, database, cache,
  messaging, gitignore, tfvars.example), `templates/generate/docs/` (GUIDE,
  README), `templates/generate/scripts/` (postgres, redis).
- `knowledge/generate/generate-routing.json` (template selection + var sources +
  unmapped→warning), `schemas/generation-warnings.schema.json`.

**New taxonomy concept:** `templates/` — the GENERATED-OUTPUT content home (added
to INTERPRETER as the `_templates` key + the taxonomy spec). Templates are DATA
(output skeletons with `{{key}}`), distinct from knowledge (lookup data); the
fragment is the routing ALGORITHM. This is the knowledge-separation rule applied
to the generate phase: ~600 lines of upstream HCL/markdown/bash became referenced
templates, leaving the fragments as thin routing.

## Cold-LLM test: PASS (after one real defect fixed)

Against the acme-store design (Fargate web+worker, ALB, Aurora, ElastiCache,
CloudWatch-Logs/papertrail; new_vpc; Private Space → restricted SG), a cold LLM
executed generate end-to-end:

- **Template selection deterministic from the routing JSON:** vpc-new (not
  existing), security-restricted (Private Space), compute/database/cache emitted,
  messaging skipped — no guessing.
- **Per-service template fill correct:** web Fargate has port-mapping +
  load_balancer blocks, worker has neither; database selected the Aurora block
  (NOT RDS), rds_proxy tail omitted (false); cache `num_cache_clusters=2`
  (multi_az). No `{{placeholder}}` left.
- **Papertrail CloudWatch-Logs integrated, not warned** (per the routing
  `no_warn`). 6/6 services generated-or-warned; `generation-warnings.json` empty.
- **Docs conditional sections correct:** Postgres+Redis sections included, Kafka
  omitted, Containerization Prereqs included (buildpack_only), Platform Risk +
  interim sections omitted (full_cutover), Manual Items omitted (no deferred).
  README lists only emitted files; both scripts written.
- **The cross-artifact assembler is a GENUINE validator** (coverage + README-refs
  - placeholder-leak across both fragments + the input) — unlike the no-op/promote
    assemblers of clarify/design/estimate. → HANDOFF_OK.

## The defect (real, apply-blocking, FIXED)

The cold LLM caught a genuine correctness bug, not a determinism nit: the
**restricted security template defined only `aws_security_group.app`**, but the
domain templates (compute/database/cache) reference the per-tier SGs
`aws_security_group.fargate/alb/database/cache`. So the generated Terraform for
ANY Private-Space migration referenced UNDECLARED security groups → `terraform
validate` would fail — and the no-`{{}}`-leak gate didn't catch it (these are
real HCL refs, not placeholders). Inherited from the upstream split, which never
generated both files in one validated pass.

**Fix (two layers):**

1. Rewrote `security-restricted.tf.tmpl` to declare the SAME tiered SGs as
   standard (so domain references resolve); the ONLY "restricted" difference is
   the ALB external ingress (declared dependency CIDRs via `var.app_ingress_rules`
   instead of `0.0.0.0/0`). Inter-tier SGs (fargate←alb, db/cache/msk←fargate)
   unchanged.
2. Added a REFERENCE-INTEGRITY postcondition to BOTH the terraform fragment
   (write-time) and the assembler (cross-artifact): every `aws_security_group.X`
   reference must resolve to a declared SG — fail-closed. This closes the gap
   that let the no-`{{}}` gate miss it.

**Re-test: PASS** — all domain SG references resolve, the new gate is present in
both units and fail-closed, no regression (no duplicate resource, no unfilled
placeholder). One non-blocking note: both security templates are skeletons listing
all tier SG blocks; the interpreter drops absent-tier blocks during fill (an
unused tier SG would still `validate`).

## Net

Generate is ported and cold-validated. The multi-fragment + multi-artifact +
templates-as-knowledge shape works: the routing JSON drove every variant /
conditional-block / per-service-fill decision deterministically, and the
cross-artifact assembler is the taxonomy's first real validator (coverage,
reference integrity, placeholder leak across both fragments). The probe-style
cold test earned its keep again — catching an apply-blocking dangling-SG defect
that no `{{}}`-gate would find, now fixed + guarded by a reference-integrity
postcondition. `templates/` is established as the generated-output home. EKS
generate is a gated stub (the EKS cross-phase pass remains: design branch +
estimate handling (authored) + this). Next: feedback (the last phase) — small,
LLM-driven.
