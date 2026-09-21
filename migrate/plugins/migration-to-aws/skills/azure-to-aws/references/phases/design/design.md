---
_phase: design
_title: "Design AWS Architecture"
_requires_phase: clarify
_input:
  - azure-resource-inventory.json
  - preferences.json
_fragments:
  - _id: mapping-engine
    _trigger: { _always: true }
    _file: phases/design/design-mapping.md
_assemble:
  _file: phases/design/design-assemble.md
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
  - _check_file_exists: [azure-resource-inventory.json, preferences.json]
    _on_failure: _unrecoverable
  - _validate_json: [azure-resource-inventory.json, preferences.json]
    _on_failure: _unrecoverable
_postconditions:
  - _check_file_exists: aws-design.json
    _on_failure: _halt_and_inform
  - _validate_json: aws-design.json
    _on_failure: _halt_and_inform
  - _assert: "aws-design.json has phase == 'design' and a valid timestamp; services[] is present (empty only if all resources deferred)"
    _on_failure: _halt_and_inform
  - _assert: "every services[] entry has service_id, source_resource_id, azure_resource_type, aws_service, confidence, and aws_config"
    _on_failure: _halt_and_inform
  - _assert: "every deferred[] entry has resource_id, azure_resource_type, reason, and recommendation"
    _on_failure: _halt_and_inform
  - _assert: "vpc_design is present with a valid mode (existing_vpc or new_vpc)"
    _on_failure: _halt_and_inform
  - _assert: "metadata.total_services matches services[].length"
    _on_failure: _halt_and_inform
  - _assert: "no azurerm_windows_web_app resource is mapped to a non-detect_only service (detect_only in v1)"
    _on_failure: _halt_and_inform
  - _assert: "no azurerm_kubernetes_cluster resource is mapped to a primary service (detect_only in v1)"
    _on_failure: _halt_and_inform
  - _assert: "no azurerm_cosmosdb_account resource is mapped to a primary service (specialist gate in v1)"
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

Single-pass mapping engine: translate each Azure resource to its AWS equivalent using the
deterministic lookup table in `design-mapping.md`. No clustering, no dependency graphs —
resources are processed as a flat list in input order.

Composed of one mapping fragment + one assembler (declared in the frontmatter
`_fragments`/`_assemble`); the interpreter runs the fragment, then the assembler.

The compute target for web apps and container apps is read from
`preferences.design_constraints.compute_target.default`:

- `ecs-fargate` (default): `azurerm_linux_web_app` and `azurerm_container_app` → ECS Fargate.
- `elastic_beanstalk`: `azurerm_linux_web_app` → Elastic Beanstalk (Docker, AL2023).

---

## Scope Boundary

**This phase covers Azure → AWS Design ONLY.**

FORBIDDEN — Do NOT include cost estimates, Terraform generation, migration scripts,
feedback collection, or clarify questions.

**Your ONLY job: Map each Azure resource to its AWS equivalent. Nothing else.**
