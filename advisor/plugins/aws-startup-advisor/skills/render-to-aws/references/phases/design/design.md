---
_phase: design
_title: "Design AWS Architecture"
_requires_phase: clarify
_input:
  - render-resource-inventory.json
  - preferences.json
_knowledge:
  - { file: knowledge/design/web-service-eb-sizing.json, _when: "inventory has a web_service AND (design_constraints.compute_target.default is elastic_beanstalk OR design_constraints.compute_target is absent)" }
  - { file: knowledge/design/web-service-fargate-sizing.json, _when: "inventory has a web_service AND (design_constraints.compute_target.default is ecs-fargate OR design_constraints.compute_target is absent)" }
  - { file: knowledge/design/worker-fargate-sizing.json, _when: "inventory has a background_worker" }
  - { file: knowledge/design/cron-lambda-sizing.json, _when: "inventory has a cron_job" }
  - { file: knowledge/design/postgres-rds-sizing.json, _when: "inventory has a postgres service" }
  - { file: knowledge/design/redis-elasticache-sizing.json, _when: "inventory has a key_value service" }
_fragments:
  - _id: mapping-engine
    _trigger: { _always: true }
    _file: phases/design/design-mapping.md
_assemble:
  _file: phases/design/design-mapping.md
_produces:
  - aws-design.json
_advances_to: estimate
_re_entry_guard:
  _stale_if_completed: estimate
  _stale_artifact: estimation-infra.json
  _on_reentry: stop_unless_confirmed
  _on_confirm: reset_downstream_to_pending
_preconditions:
  - _check_phase_completed: clarify
    _on_failure: _halt_and_inform
  - _check_single_active_phase: true
    _on_failure: _halt_and_inform
  - _check_file_exists: [render-resource-inventory.json, preferences.json]
    _on_failure: _unrecoverable
  - _validate_json: [render-resource-inventory.json, preferences.json]
    _on_failure: _unrecoverable
_postconditions:
  - _check_file_exists: aws-design.json
    _on_failure: _halt_and_inform
  - _validate_json: aws-design.json
    _on_failure: _halt_and_inform
  - _assert: "aws-design.json has phase == 'design' and a valid timestamp; services[] is present (empty only if all resources deferred)"
    _on_failure: _halt_and_inform
  - _assert: "every services[] entry has service_id, source_resource_id, render_service, aws_service, confidence, aws_config; every deferred[] entry has service_name, service_type, plan, reason, recommendation"
    _on_failure: _halt_and_inform
  - _assert: "vpc_design is present with a valid mode (existing_vpc or new_vpc); if new_vpc then at least 2 subnets across separate AZs"
    _on_failure: _halt_and_inform
  - _assert: "metadata.total_services matches services[].length"
    _on_failure: _halt_and_inform
  - _assert: "every background_worker service maps to aws_service == 'Fargate' (background workers are always Fargate)"
    _on_failure: _halt_and_inform
  - _assert: "no static_site or private_service maps to an AWS service (they must be in deferred[])"
    _on_failure: _halt_and_inform
_forbids_files:
  - README.md
  - "*.txt"
  - "terraform/**"
  - MIGRATION_GUIDE.md
  - estimation-infra.json
---

# Phase 3: Design AWS Architecture

## Orientation

Single-pass mapping engine: translate each Render service to its AWS equivalent
using deterministic lookup tables. No clustering, no dependency graphs — services
are processed as a flat list in input order.

The mapping fragment (`design-mapping.md`) runs and produces `aws-design.json`.
The `_knowledge` guards load only the sizing tables the inventory needs. The compute
target branch is selected by `design_constraints.compute_target`:

- **Web Services**: Elastic Beanstalk (default) or Fargate override
- **Background Workers**: always Fargate (no override)
- **Cron Jobs**: EventBridge Scheduler + Lambda (default) or Fargate Scheduled Tasks
- **PostgreSQL**: RDS PostgreSQL (single-az/multi-az) or Aurora (multi-az-ha)
- **Key Value (Redis)**: ElastiCache Redis

**Out of scope in v1:** `static_site` and `private_service` go to `deferred[]` with
`reason: "out of scope in v1"` and a recommendation (CloudFront+S3 for static sites).

---

## Scope Boundary

**This phase covers Render → AWS Design ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Cost estimates or pricing calculations (that is Phase 4 — Estimate)
- Terraform generation or HCL code (that is Phase 5 — Generate)
- Migration scripts or runbooks (that is Phase 5 — Generate)
- Data migration procedures (that is Phase 5 — Generate)
- Feedback collection (that is Phase 6 — Feedback)
- Clarify questions or preference gathering (that is Phase 2 — Clarify)
- Resource discovery (that is Phase 1 — Discover)

**Your ONLY job: Map each Render service to its AWS equivalent. Nothing else.**
