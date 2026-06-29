---
_fragment: mapping-engine
_of_phase: design
_scope: >
  Single-pass map each inventory resource to its AWS equivalent via the
  knowledge/design lookup tables, design the VPC + security groups, and note Fir
  workloads as deferred. Writes aws-design.json. ONLY this — no cost, no
  Terraform, no scripts. Does NOT update .phase-status.json.
_produces: [aws-design.json]
_postconditions:
  - _validate_json: aws-design.json
  - _assert: "aws-design.json has phase=='design', a timestamp, services[], deferred[], warnings[], metadata, vpc_design"
  - _assert: "services[] is empty ONLY if every resource deferred; otherwise has >=1 entry"
  - _assert: "every services[] entry has service_id, source_resource_id, heroku_app, aws_service, confidence, aws_config"
  - _assert: "every deferred[] entry has addon_name, addon_plan, provider, reason, recommendation"
  - _assert: "vpc_design.mode is 'existing_vpc' or 'new_vpc'"
  - _assert: "metadata.total_services == services[].length"
  - { _assert: "no ARM/Graviton/CNB targeting anywhere in output (Fir is detect-only)", _on_failure: _unrecoverable }
_on_error:
  _warn_and_skip:    { effect: "record warning; skip this resource; continue",        status: continue }
  _defer:            { effect: "append a deferred[] entry; continue",                  status: continue }
  _default_and_warn: { effect: "apply documented default; record warning; continue",   status: continue }
  _halt_and_inform:  { effect: "stop; surface diagnostic",                             status: retain_in_progress }
  _unrecoverable:    { effect: "stop; surface error",                                  status: revert_to_pending }
---

# Design Fragment: Mapping Engine (Fargate path)

## Orientation

The single design-phase FRAGMENT (Fargate compute path), triggered always by
`design.phase.md`. It reads `heroku-resource-inventory.json` + `preferences.json`
and, in one deterministic pass over the resources (flat, input order), maps each
to its AWS equivalent, designs the VPC + security groups, and notes Fir —
creating `aws-design.json` (the assembler validates it + the route gates after).

Where things live: tunable constants (engine versions, VPC topology, ports,
patterns, fixed messages) are in `knowledge/design/design-defaults.json`; the
lookup tables are the other `knowledge/design/*.json` files; the output artifact
SHAPE is the contract in `schemas/aws-design.schema.json`. See
`docs/unit-taxonomy-spec.md` → knowledge/contract/procedure separation for why.

## Step: init_output_and_prefs

```meta
_writes_var: design
```

Initialize the in-run `design` object:

```json
{
  "phase": "design",
  "design_source": "<inventory metadata.discovery_sources[0] or 'terraform'>",
  "timestamp": "<current ISO 8601 UTC>",
  "metadata": {
    "total_services": 0,
    "total_apps_migrated": 0,
    "fir_workloads_detected": [],
    "fir_generation_note": ""
  },
  "services": [],
  "deferred": [],
  "warnings": [],
  "vpc_design": {}
}
```

Read from `preferences.json` (used by later steps; resolve once here):
`global.target_region` (→ `region` for all services), `global.availability`,
`data.database_ha` (overrides availability for the DB only, if present),
`data.redis_ha`, `operational.log_retention_days`,
`design_constraints.kubernetes.value`, `operational.fir_intent` (may be absent).

**Compute-mode determination (EKS gate):** if
`design_constraints.kubernetes.value` is `eks-managed` or `eks-or-ecs`, the EKS
compute path is active — SKIP the `formation` Fargate branch below entirely (the
`eks-mapping` fragment maps formations to EKS pods and the assembler folds them
in). Still do everything else here: non-formation services (postgres/redis/kafka/
fast-path), VPC, Fir. If the value is `ecs-fargate` or absent, run the Fargate
formation branch as normal. Fir-intent precedence:
`operational.fir_intent == "self_managed_eks_ecs"` does NOT by itself enable EKS;
the global kubernetes preference governs. Fir stays a deferred notation
(Step `note_fir`).

## Step: map_resources

```meta
_for_each: inventory.resources
_branch_on: resource_type
_branch_cases: [formation, addon, pipeline, space, _default]
_collect: [services, deferred, warnings, spaces]
_knowledge: [knowledge/design/design-defaults.json, knowledge/design/dyno-fargate-sizing.json, knowledge/design/postgres-rds-sizing.json, knowledge/design/redis-elasticache-sizing.json, knowledge/design/kafka-msk-sizing.json, knowledge/design/fast-path-addons.json]
```

Process each resource in `inventory.resources[]` in INPUT ORDER. Branch on
`resource_type` (`_branch_on`); the per-case handling is the prose below (FORM
2b — the body prose IS the case bodies). Cases handled: `formation`, `addon`,
`pipeline`, `space`; everything else falls to the default (skip). Each branch
consults its table from `_knowledge`.

DETERMINISM RULE (binding for every branch below): each numeric/string result
MUST be a DIRECT LOOKUP from the matched knowledge-table row, a documented clamp,
or a documented tier branch. Do NOT recompute a table value from its provenance
columns — `heroku_*`, `memory_limit`, `throughput`, and `src_connection_pooling`
are provenance only. A lookup is a lookup; a clamp is a clamp.

For each branch:

**`formation` →** Fargate mapping (DEFAULT compute path — SKIP this entire branch
when the EKS gate is active; the `eks-mapping` fragment handles formations then):

1. If the app has NO formation resources at all (empty Procfile), reject the
   app's formations: warn with `design-defaults.json.messages.empty_procfile` `[_uses: design-defaults.json]`
   (filling `{app}`) and skip. (`_warn_and_skip`)
2. Look up `config.dyno_type` in `dyno-fargate-sizing.json.rows` `[_uses: dyno-fargate-sizing.json]` (exact,
   case-insensitive). NOT found → reject this formation, warn per the table's
   `_on_not_found`, produce NO entry, continue. (`_warn_and_skip`)
3. Found → read `fargate_cpu` + `fargate_memory` DIRECTLY from the matched row
   (do NOT recompute from `heroku_*`).
4. `desired_count` = `config.quantity`, clamped to the dyno table's
   `_desired_count` min/max. If out of range, clamp to the nearest boundary AND
   warn. (`_default_and_warn`)
5. Append a Fargate service entry (shape per `aws-design.schema.json`):
   `service_id` = `fargate:{app}:{process_type}`, `aws_service` = `Fargate`,
   `confidence` = `deterministic`, `aws_config` carries `region`, the
   looked-up `task_cpu`/`task_memory`, `desired_count`, `process_type`,
   `container_image` per `design-defaults.json.patterns.container_image`, and
   `load_balancer` = true iff `process_type == "web"`.
6. If `process_type == "web"`, ALSO append an ALB entry: `service_id` =
   `alb:{app}:{process_type}`, `aws_service` = `ALB`, `aws_config.target_group`
   = the web Fargate `service_id`, `scheme` = `internet-facing`.

**`addon` →** branch on `config.addon_service`:

- **`heroku-postgresql`** — look up `config.plan` in `postgres-rds-sizing.json` `[_uses: postgres-rds-sizing.json]`
  (exact, case-insensitive). NOT found → `_defer` (specialist gate) + warn per
  the table. Found → select engine via the table's `_engine_selection` (source =
  `data.database_ha` if set else `global.availability`; unset/unrecognized →
  default `multi-az` + RDS + warn). RDS uses `rds_instance_class`, Aurora uses
  `aurora_instance_class`. `multi_az: true` when availability ∈
  {multi-az,multi-az-ha,multi-region}. `storage_gb` from the row (allocate ≥).
  `rds_proxy` per the table's `_rds_proxy`. Append an entry (shape per
  `aws-design.schema.json`): `service_id` = `rds:{app}:postgres`, `aws_service`
  = `RDS PostgreSQL` or `Aurora PostgreSQL`, `aws_config` with `region`,
  `instance_class` (from the selected column), `multi_az`, `storage_gb`,
  `rds_proxy`, and `engine_version` from
  `design-defaults.json.engine_versions.rds_postgresql`.

- **`heroku-redis`** — look up `config.plan` in `redis-elasticache-sizing.json` `[_uses: redis-elasticache-sizing.json]`.
  NOT found → `_defer` + warn. Found → append an entry (shape per the schema):
  `service_id` = `elasticache:{app}:redis`, `aws_service` = `ElastiCache Redis`,
  `aws_config` with `region`, `node_type` from the row, `multi_az` +
  `automatic_failover` per the table's `_ha` (row `ha` OR `config.ha_enabled`),
  `transit_encryption` per `_transit_encryption`, and `engine_version` from
  `design-defaults.json.engine_versions.elasticache_redis` `[_uses: design-defaults.json]`
  (pinned; the row `redis_version` is provenance only).

- **`heroku-kafka`** — look up `config.plan` in `kafka-msk-sizing.json` `[_uses: kafka-msk-sizing.json]`. NOT
  found → `_defer` + warn. Found → append an entry (shape per the schema):
  `service_id` = `msk:{app}:kafka`, `aws_service` = `Amazon MSK`, `aws_config`
  with `region`, `broker_instance_type` + `storage_per_broker_gb` from the row,
  `broker_count`/`availability_zones` per the table's `_broker_count_and_azs`,
  and `max_topics`/`max_partitions`/`replication_factor` per
  `_topology_preservation`.

- **any other `addon_service`** — fast-path: NORMALIZE the name per
  `fast-path-addons.json._normalize` `[_uses: fast-path-addons.json]` + `_prefix_aliases`, then EXACT
  case-insensitive match against `rows` (partial matches INVALID). Matched →
  `single` produces one entry, `composite` produces one entry listing all
  `aws_services`; confidence `deterministic`. Use a DETERMINISTIC `service_id`:
  `{primary_aws_service_snake}:{app}:{addon_service}`, where
  primary_aws_service is the first entry in the row's `aws_services` lowercased
  with non-alphanumerics → `-` ("CloudWatch Logs" → `cloudwatch-logs`, "Amazon
  OpenSearch" → `amazon-opensearch`). `aws_config` ALWAYS carries `region` plus,
  by mapping type:
  - CloudWatch / CloudWatch Logs single → `log_group` per
    `design-defaults.json.patterns.cloudwatch_log_group` (filling `{app}`) and
    `retention_days` = `operational.log_retention_days` else
    `design-defaults.json.patterns.default_log_retention_days`.
  - composite → `services: [<all aws_services>]`.
  - any other single → just `region` (the AWS service name lives in
    `aws_service`; do NOT invent service-specific keys). NOT matched → `_defer`
    (specialist gate) with the table's deferred record shape.

**`pipeline` →** detect-only. NO service entry. Warn with
`design-defaults.json.messages.pipeline_detect_only` (filling `{pipeline}` =
`config.pipeline_name`).

**`space` →** collect into `spaces` for the post-loop VPC step. No entry here.

**`_default` (app, domain, config) →** no AWS service mapping in this phase; skip.

Append produced entries to `services`/`deferred`; collect `warnings`. EVERY
entry appended to `services[]` counts toward `metadata.total_services` —
INCLUDING the separate ALB entry for a web formation (a web formation therefore
contributes TWO services: the Fargate task and its ALB). `total_services` is the
true length of `services[]`; recompute it in `finalize_and_write`.

## Step: design_vpc

```meta
_writes_var: design
_knowledge: [knowledge/design/design-defaults.json]
```

After the loop, design `design.vpc_design` from the collected `spaces` +
`preferences.network`:

1. **Mode:** if any space has `config.peering.detected == true` with a valid
   `vpc_id` → `existing_vpc` (use that `vpc_id` + `preferences.network.subnet_ids`).
   Else (no peering / no spaces) → `new_vpc`.
2. **existing_vpc:** `{ mode, existing_vpc_id, subnet_ids, security_groups }`
   (use the space `vpc_id` + `preferences.network.subnet_ids`).
3. **new_vpc:** build from `design-defaults.json.new_vpc` `[_uses: design-defaults.json]` — `cidr_block`, the
   `subnets` list (each subnet's `az` = `{target_region}` + the row's
   `az_suffix`, with its `cidr`/`type`), `route_table`, and `internet_gateway`.
   Plus `security_groups`.
4. **Security groups** — from `design-defaults.json.security_group`:
   - If migrating from a Private Space (any space present, either mode):
     RESTRICTED inbound — implicit deny otherwise; egress = `outbound_all`. SG
     `name` per `restricted_name_pattern` (`{primary_app}` = first app with a
     mapped service, else `fallback_primary_app`). Add an inbound rule for a
     `ports` entry ONLY when its `include_port_when` condition holds for THIS
     design: `app_https` (always), `postgres` (if an RDS/Aurora service exists),
     `redis` (if ElastiCache exists), `kafka` (if MSK exists). Rule `cidr`
     resolves `restricted_cidr_source` mechanically: use its `primary` field-path
     (`space.config.peering.peer_cidr`) if non-null, else its `fallback`
     (`vpc_design.cidr_block`) `[_uses: design-defaults.json]`. Do NOT substitute
     any other CIDR.
   - If NO Private Space: default SG `name` per `default_name_pattern` — inbound
     `app_https` + `app_http`, each with `cidr` = `default_inbound_cidr`
     (`0.0.0.0/0`) verbatim `[_uses: design-defaults.json]`; egress =
     `outbound_all`. Do NOT substitute the VPC CIDR or any other value.

## Step: note_fir

```meta
_writes_var: design
_knowledge: [knowledge/design/design-defaults.json]
```

Scan `inventory.apps[]` for `heroku_generation == "fir"`.

- Fir apps exist → add each name to `metadata.fir_workloads_detected[]`; set
  `metadata.fir_generation_note` to `design-defaults.json.fir.deferral_note` `[_uses: design-defaults.json]`;
  add a warning listing the app names.
- No Fir → `fir_workloads_detected: []`, note =
  `design-defaults.json.fir.none_note`.
- **HARD CONSTRAINT:** NEVER emit ARM/Graviton instance targeting or CNB
  buildpack config anywhere, regardless of generation. Detect-only.

## Step: finalize_and_write

```meta
_writes: aws-design.json
```

1. `metadata.total_apps_migrated` = count of distinct `heroku_app` with ≥1
   mapped service.
2. `metadata.total_services` = `services[].length`.
3. `timestamp` = current ISO 8601 UTC; `design_source` =
   `inventory.metadata.discovery_sources[0]` (or `"terraform"`).
4. Write the `design` object to `$MIGRATION_DIR/aws-design.json`.

If NEITHER any `services[]` NOR any `deferred[]` entry was produced, that is an
`_unrecoverable` error (nothing was designed).
