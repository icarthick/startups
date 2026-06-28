---
# ============================================================================
# generate.phase.md — Phase 5 (Generate).
# THIN phase. The MULTI-ARTIFACT phase: it emits terraform/ (many .tf files),
# MIGRATION_GUIDE.md, README.md, scripts/, and generation-warnings.json.
#
# TWO fragments (independent reasons-to-change, different output sets):
#   - generate-terraform : routes design -> templates/generate/terraform/*.tmpl,
#                          writes terraform/ + generation-warnings.json
#   - generate-docs      : fills templates/generate/docs + scripts templates,
#                          writes MIGRATION_GUIDE.md, README.md, scripts/
# Plus a CROSS-ARTIFACT validator assembler (every-service-generated-or-warned,
# README refs exist, no {{VAR}} leak, required files present) — the taxonomy's
# first non-trivial multi-artifact assembler.
#
# Templates are DATA (templates/generate/...), referenced via _templates; the
# fragments are the routing ALGORITHM (see docs/unit-taxonomy-spec.md). Routing
# data + var sources are knowledge/generate/generate-routing.json.
#
# EKS generate (eks.tf + kubernetes/ manifests) is a loud-halt stub, gated like
# design's EKS branch — part of the later EKS cross-phase pass.
# ============================================================================
_phase: generate
_title: "Generate Migration Artifacts"
_requires_phase: estimate
_scope: >
  Transform the design + estimate into deployable artifacts: a terraform/
  directory, MIGRATION_GUIDE.md, README.md, database migration scripts, and
  generation-warnings.json. ONLY this. No re-design, no re-estimate, no new
  clarify questions, no discovery, no feedback collection.

_input:
  - aws-design.json
  - estimation-infra.json
  - preferences.json
  - heroku-resource-inventory.json

_knowledge:
  - { file: knowledge/generate/generate-routing.json }

_templates:
  - { file: templates/generate/terraform/main.tf.tmpl }
  - { file: templates/generate/terraform/variables.tf.tmpl }
  - { file: templates/generate/terraform/outputs.tf.tmpl }
  - { file: templates/generate/terraform/gitignore.tmpl }
  - { file: templates/generate/terraform/tfvars.example.tmpl }
  - { file: templates/generate/terraform/vpc-new.tf.tmpl,       _when: "vpc_design.mode == new_vpc" }
  - { file: templates/generate/terraform/vpc-existing.tf.tmpl,  _when: "vpc_design.mode == existing_vpc" }
  - { file: templates/generate/terraform/security-restricted.tf.tmpl, _when: "a Private Space exists" }
  - { file: templates/generate/terraform/security-standard.tf.tmpl,   _when: "no Private Space" }
  - { file: templates/generate/terraform/compute.tf.tmpl,   _when: "design has Fargate or ALB" }
  - { file: templates/generate/terraform/database.tf.tmpl,  _when: "design has RDS or Aurora" }
  - { file: templates/generate/terraform/cache.tf.tmpl,     _when: "design has ElastiCache" }
  - { file: templates/generate/terraform/messaging.tf.tmpl, _when: "design has MSK" }
  - { file: templates/generate/docs/MIGRATION_GUIDE.md.tmpl }
  - { file: templates/generate/docs/README.md.tmpl }
  - { file: templates/generate/scripts/migrate-postgres.sh, _when: "design has Postgres" }
  - { file: templates/generate/scripts/migrate-redis.sh,    _when: "design has Redis" }

_re_entry_guard:
  if: "feedback.json exists AND phase feedback completed"
  action: _halt_and_inform
  reason: stale_downstream
  on_confirm: >
    Reset phase feedback to "pending" in .phase-status.json (leave generate as
    the active in_progress phase), and remove feedback.json from $MIGRATION_DIR/
    if present. The generated terraform/, docs, and scripts ARE this phase's own
    artifacts and are overwritten by the re-run. Then run generate normally.
    NEVER perform this reset without the user's explicit confirmation.

_preconditions:
  - _check_single_active_phase: true
    _on_failure:
      _halt_and_inform: >
        Another core phase is already in_progress. Resolve it before re-running
        generate.
  - _check_phase_completed: estimate
    _on_failure:
      _halt_and_inform: >
        Estimate has not completed. Run Phase 4 (estimate.phase.md) first.
  - _check_file_exists: [aws-design.json, estimation-infra.json, preferences.json, heroku-resource-inventory.json]
    _on_failure:
      _unrecoverable: >
        A required input is missing. All four (aws-design, estimation-infra,
        preferences, inventory) are required.
  - _validate_json: [aws-design.json, estimation-infra.json, preferences.json]
    _on_failure:
      _unrecoverable: "An input file does not parse as valid JSON. Re-run its producing phase."
  - _check_source_exists: { glob: "aws-design.json", containing: '"services"' }
    _on_failure:
      _unrecoverable: "aws-design.json has no services[]. Re-run design."

# TWO fragments + one cross-artifact assembler. The eks-generate fragment is
# trigger-gated on an EKS design entry and is NOT YET AUTHORED (loud-halt stub).
_fragments:
  - _id: terraform
    _trigger: { _always: true }
    _file: phases/generate/generate-terraform.md
  - _id: docs
    _trigger: { _always: true }
    _file: phases/generate/generate-docs.md
  - _id: eks-generate
    _trigger: { _when: "aws-design.json has an eks_cluster entry OR a service with aws_service == 'EKS'" }
    _file: phases/generate/generate-eks.md

_assemble:
  _file: phases/generate/generate-assemble.md

_postconditions:
  - _check_file_exists: [terraform/main.tf, MIGRATION_GUIDE.md, README.md]
  - _assert: "generation-warnings.json exists (empty warnings[] if all services generated)"

_produces:
  - terraform/
  - MIGRATION_GUIDE.md
  - README.md
  - scripts/
  - generation-warnings.json
_advances_to: feedback
_forbids_files:
  - "*.txt"
  - feedback.json

_on_error:
  _warn_and_skip:   { effect: "log to generation-warnings.json; skip this service; continue", status: continue }
  _halt_and_inform: { effect: "stop; surface diagnostic",                                     status: retain_in_progress }
  _unrecoverable:   { effect: "stop; surface error",                                          status: revert_to_pending }
---

# Generate Migration Artifacts

## Orientation

Transform the design + estimate into deployable artifacts in `$MIGRATION_DIR/`.
This is the MULTI-ARTIFACT phase. The work is TWO FRAGMENTS + one ASSEMBLER:

1. **terraform** fragment (`phases/generate/generate-terraform.md`) — the routing
   algorithm: select `templates/generate/terraform/*.tmpl` per the design (via
   `knowledge/generate/generate-routing.json`), fill `{{placeholders}}`, write the
   `terraform/` directory, and log unmapped services to `generation-warnings.json`.
2. **docs** fragment (`phases/generate/generate-docs.md`) — fill the doc + script
   templates (`templates/generate/docs/`, `templates/generate/scripts/`) with
   conditional sections, writing `MIGRATION_GUIDE.md`, `README.md`, and the
   `scripts/` migration scripts.
3. **generate-assemble** (`phases/generate/generate-assemble.md`) — the
   cross-artifact validator: every designed service is generated OR warned;
   `README.md` references only files that exist; no `{{VAR}}` placeholder leaks
   into `.tf` files; the required file set is present.

Templates are DATA (output skeletons, referenced via `_templates`, never inlined);
the routing/var-source mapping is `knowledge/generate/generate-routing.json`; the
warnings SHAPE is `schemas/generation-warnings.schema.json`. EKS generation
(`generate-eks.md`) is a loud-halt stub gated on an EKS design entry — not yet
authored (the Fargate path is complete). After the assembler validates, the phase
emits `HANDOFF_OK | phase=generate | ...`, sets `phases.generate="completed"`,
`current_phase="feedback"`, and tells the user to load `feedback.phase.md` next.
