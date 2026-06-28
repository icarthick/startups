---
_fragment: terraform
_of_phase: generate
_scope: >
  Route the design to terraform templates, fill placeholders, write the
  terraform/ directory, and log unmapped services to generation-warnings.json.
  ONLY this — no docs, no scripts, no re-design. Does NOT update .phase-status.json.
_produces: [terraform/, generation-warnings.json]
_postconditions:
  - _check_file_exists: [terraform/main.tf, terraform/variables.tf, terraform/outputs.tf]
  - _assert: "terraform/security.tf exists (always) and exactly one terraform/vpc.tf exists"
  - _assert: "at least one domain file (compute.tf/database.tf/cache.tf/messaging.tf) exists when the design has that service type"
  - _assert: "no {{...}} placeholder remains in any written .tf file"
  - _assert: "every aws_security_group.<name> referenced in a written domain .tf resolves to an SG declared in the emitted security.tf (no dangling SG reference)"
  - _assert: "generation-warnings.json exists and validates against schemas/generation-warnings.schema.json"
  - { _assert: "every aws-design service is either generated in a .tf or listed in generation-warnings.json", _on_failure: _warn_and_skip }
_on_error:
  _warn_and_skip:   { effect: "log to generation-warnings.json; skip this service; continue", status: continue }
  _unrecoverable:   { effect: "stop; surface error",                                          status: revert_to_pending }
---

# Generate Fragment: Terraform

## Orientation

The terraform-generation FRAGMENT, triggered always by `generate.phase.md`. It is
the ROUTING ALGORITHM: reads `aws-design.json` + `preferences.json`, consults
`knowledge/generate/generate-routing.json` for template selection + variable
sources, fills the `templates/generate/terraform/*.tmpl` skeletons, and writes the
`terraform/` directory plus `generation-warnings.json`. The HCL bodies are
templates (data); this fragment only selects, fills, and routes. Does NOT update
`.phase-status.json`.

## Step: emit_core_and_vpc

```meta
_knowledge: [knowledge/generate/generate-routing.json]
_templates: [templates/generate/terraform/main.tf.tmpl, templates/generate/terraform/variables.tf.tmpl, templates/generate/terraform/outputs.tf.tmpl, templates/generate/terraform/gitignore.tmpl, templates/generate/terraform/tfvars.example.tmpl, templates/generate/terraform/vpc-new.tf.tmpl, templates/generate/terraform/vpc-existing.tf.tmpl, templates/generate/terraform/security-restricted.tf.tmpl, templates/generate/terraform/security-standard.tf.tmpl]
```

Emit the `always_emit` templates from the routing (main/variables/outputs/
.gitignore/tfvars.example), filling their `{{placeholders}}` from
`generate-routing.json.template_var_sources` (resolved against
`preferences.json`, `aws-design.json`, `.phase-status.json`).

Then emit EXACTLY ONE `vpc.tf` (the `vpc-new` template when
`vpc_design.mode == "new_vpc"`, else `vpc-existing`) and EXACTLY ONE
`security.tf` (the `security-restricted` template when a Private Space exists in
the design, else `security-standard`). Resolve `{{vpc_id_reference}}` to
`aws_vpc.main.id` (new) or `data.aws_vpc.existing.id` (existing), and
`{{app_ingress_rules_hcl}}` / `{{existing_subnet_ids_hcl_list}}` from the design's
`vpc_design`.

## Step: emit_domain_files

```meta
_for_each: design.services
_collect: [generated, warnings]
_knowledge: [knowledge/generate/generate-routing.json]
_templates: [templates/generate/terraform/compute.tf.tmpl, templates/generate/terraform/database.tf.tmpl, templates/generate/terraform/cache.tf.tmpl, templates/generate/terraform/messaging.tf.tmpl]
```

Route each service in `aws-design.json.services[]` by `aws_service` per
`generate-routing.json.service_to_file`, and emit the domain file once per
present type (compute.tf for Fargate/ALB, database.tf for RDS/Aurora, cache.tf
for ElastiCache, messaging.tf for MSK). Within each domain template, fill the
REPEAT blocks once per matching service, resolving per-service `{{placeholders}}`
from each service's `aws_config` (per `template_var_sources`):

- **compute**: cluster + per-Fargate-service log group / task def / service;
  include the `{{port_mappings_block}}` only for `process_type == "web"`, and the
  `{{load_balancer_block}}` only when `aws_config.load_balancer == true`; emit ALB
  resources per web service. `{{private_subnet_refs}}`/`{{public_subnet_refs}}`
  resolve per `vpc_design.mode`.
- **database**: select the RDS block (`aws_service == "RDS PostgreSQL"`) XOR the
  Aurora block (`"Aurora PostgreSQL"`); append the RDS Proxy block only when
  `aws_config.rds_proxy == true`. `{{major_version}}` from `engine_version`.
- **cache**: `num_cache_clusters` = 2 if `multi_az` else 1; HA/encryption from
  `aws_config`.
- **messaging**: `{{retention_hours}}` = `preferences.data.kafka_retention_days *
  24`; broker count/type/storage from `aws_config`.

**Unmapped services**: for any `aws_service` in
`generate-routing.json.unmapped_to_warning.warn_services` (e.g. SES, SNS,
EventBridge, MQ, OpenSearch, S3, CloudFront, composites), do NOT emit a .tf;
collect a warning. EXCEPTION: a `CloudWatch Logs` service from a logging add-on
is integrated into compute.tf's log config (`no_warn`) — do NOT warn for it.

## Step: write_warnings

```meta
_writes: generation-warnings.json
_knowledge: [knowledge/generate/generate-routing.json]
```

Write `$MIGRATION_DIR/generation-warnings.json` (shape per
`schemas/generation-warnings.schema.json`): `generated_at` (ISO 8601),
`migration_id`, `warnings[]` (one per skipped service, using the routing's
`reason_template` + `recommendation`), `total_warnings`,
`total_services_generated`, `total_services_skipped`. Write it ALWAYS — an empty
`warnings: []` when every service was generated.

Before finishing, scan every written `.tf` and confirm NO `{{...}}` placeholder
remains (all resolved to real values or `var.*` references).
