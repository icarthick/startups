---
_fragment: mapping-engine
_of_phase: design
_contributes:
  - aws-design.json
---

# Design Phase: Render → AWS Mapping Engine

> Self-contained mapping sub-file. Processes each Render service from the inventory
> using the loaded sizing tables and produces the `aws-design.json` artifact.
> Runs after `_knowledge` guards have loaded the relevant sizing tables.

**Execute ALL steps in order. Do not skip or deviate.**

---

## Step 1: Load Context

Read:

- `$MIGRATION_DIR/render-resource-inventory.json`
- `$MIGRATION_DIR/preferences.json`
- Sizing tables already loaded via `_knowledge` guards (per design.md frontmatter)

Derive the active compute target:

```
web_compute_target = preferences.design_constraints.compute_target.default
                     || "elastic_beanstalk"  (absence → default)
cron_target = preferences.operational.cron_target
              || "lambda_eventbridge"  (absence → default)
```

---

## Step 2: Map Each Service

Process services from `inventory.services[]` in input order. For each service:

### 2a. `web_service` → Elastic Beanstalk (default) or Fargate

**If `web_compute_target == "elastic_beanstalk"`:**

1. Look up the service `plan` in `knowledge/design/web-service-eb-sizing.json` → `rows[]`.
2. Match by `render_plan`. If the plan key is not found, add to `warnings[]` and skip.
3. If `preferences.workshop.cpu_architecture == "arm64"`, use `arm64_instance` field; otherwise `aws_instance_type`.
4. Produce:

```json
{
  "service_id": "design:<name>:eb",
  "source_resource_id": "<inventory service_id>",
  "render_service": "<name>",
  "aws_service": "Elastic Beanstalk",
  "confidence": "high",
  "aws_config": {
    "instance_type": "<from sizing table>",
    "environment_type": "LoadBalanced",
    "platform": "Docker running on 64bit Amazon Linux 2023",
    "min_instances": 1,
    "max_instances": 4,
    "health_check_path": "<from config.health_check_path or />"
  }
}
```

**If `web_compute_target == "ecs-fargate"`:**

1. Look up the service `plan` in `knowledge/design/web-service-fargate-sizing.json` → `rows[]`.
2. Produce:

```json
{
  "service_id": "design:<name>:fargate",
  "source_resource_id": "<inventory service_id>",
  "render_service": "<name>",
  "aws_service": "Fargate",
  "confidence": "high",
  "aws_config": {
    "task_cpu": "<from sizing table fargate_cpu>",
    "task_memory": "<from sizing table fargate_memory_mb>",
    "desired_count": "<from config.num_instances or 1>",
    "load_balancer": true
  }
}
```

**If `web_compute_target == "eks-managed"`:**

Produce EKS Deployment + Service. Use web-service-fargate-sizing.json as the pod resource approximation (cpu/memory in Kubernetes format: `"1000m"` for 1024 CPU units).

---

### 2b. `background_worker` → ECS Fargate (ALWAYS)

Background workers are **always** Fargate regardless of `compute_target.default`. This is a hard rule — no override.

1. Look up the service `plan` in `knowledge/design/worker-fargate-sizing.json` → `rows[]`.
2. Produce:

```json
{
  "service_id": "design:<name>:fargate",
  "source_resource_id": "<inventory service_id>",
  "render_service": "<name>",
  "aws_service": "Fargate",
  "confidence": "high",
  "aws_config": {
    "task_cpu": "<from sizing table fargate_cpu>",
    "task_memory": "<from sizing table fargate_memory_mb>",
    "desired_count": "<from config.num_instances or 1>",
    "load_balancer": false
  }
}
```

Add a `warnings[]` entry: ``"`<name>` is a Background Worker — always routed to Fargate (no EB override for persistent workers)"``

---

### 2c. `cron_job` → Lambda + EventBridge Scheduler (default) or Fargate Scheduled Tasks

**If `cron_target == "lambda_eventbridge"` (default):**

1. Look up the service `plan` in `knowledge/design/cron-lambda-sizing.json` → `rows[]`.
2. If `fargate_fallback == true` for this plan, upgrade to Fargate Scheduled Tasks and add a warning.
3. Produce:

```json
{
  "service_id": "design:<name>:lambda",
  "source_resource_id": "<inventory service_id>",
  "render_service": "<name>",
  "aws_service": "Lambda",
  "confidence": "high",
  "aws_config": {
    "memory_mb": "<from sizing table lambda_memory_mb>",
    "timeout_s": "<from sizing table lambda_timeout_s>",
    "schedule": "<from config.schedule — cron expression>",
    "scheduler": "EventBridge Scheduler"
  }
}
```

**If `cron_target == "fargate_scheduled"` OR fargate_fallback triggered:**

Produce Fargate Scheduled Task using worker-fargate-sizing.json for sizing.

```json
{
  "service_id": "design:<name>:fargate-cron",
  "source_resource_id": "<inventory service_id>",
  "render_service": "<name>",
  "aws_service": "Fargate Scheduled Task",
  "confidence": "high",
  "aws_config": {
    "task_cpu": "<from worker-fargate-sizing.json fargate_cpu for plan>",
    "task_memory": "<from worker-fargate-sizing.json fargate_memory_mb for plan>",
    "schedule": "<from config.schedule — cron expression>",
    "scheduler": "EventBridge Scheduler"
  }
}
```

---

### 2d. `postgres` → RDS PostgreSQL or Aurora

1. Look up the service `plan` in `knowledge/design/postgres-rds-sizing.json` → `rows[]`.
2. Determine engine based on `preferences.data.database_ha`:
   - `single-az` or `multi-az` → `aws_engine: "postgres"`, `aws_service: "RDS PostgreSQL"`
   - `multi-az-ha` or `multi-region` → `aws_engine: "aurora-postgresql"`, `aws_service: "Aurora PostgreSQL"`
3. Set `multi_az` from `preferences.data.database_ha`:
   - `single-az` → `multi_az: false`
   - `multi-az` or higher → `multi_az: true`
4. Produce:

```json
{
  "service_id": "design:<name>:rds",
  "source_resource_id": "<inventory service_id>",
  "render_service": "<name>",
  "aws_service": "RDS PostgreSQL",
  "confidence": "high",
  "aws_config": {
    "instance_class": "<from sizing table aws_instance_class>",
    "engine": "postgres",
    "engine_version": "<from config.postgres_major_version or 16>",
    "allocated_storage_gb": "<from sizing table aws_storage_gb>",
    "multi_az": true,
    "storage_type": "gp3"
  }
}
```

---

### 2e. `key_value` → ElastiCache Redis

1. Look up the service `plan` in `knowledge/design/redis-elasticache-sizing.json` → `rows[]`.
2. Set `num_cache_nodes` from `preferences.data.redis_ha`:
   - `redis_ha: false` → `num_cache_nodes: 1`, `multi_az: false`
   - `redis_ha: true` → `num_cache_nodes: 2`, `multi_az: true`
3. Produce:

```json
{
  "service_id": "design:<name>:elasticache",
  "source_resource_id": "<inventory service_id>",
  "render_service": "<name>",
  "aws_service": "ElastiCache Redis",
  "confidence": "high",
  "aws_config": {
    "node_type": "<from sizing table aws_node_type>",
    "engine_version": "7.1",
    "num_cache_nodes": 1,
    "multi_az": false
  }
}
```

---

### 2f. `static_site` → DEFERRED (out of scope v1)

Add to `deferred[]`:

```json
{
  "service_name": "<name>",
  "service_type": "static_site",
  "plan": "<plan>",
  "reason": "Static sites are out of scope in render-to-aws v1.",
  "recommendation": "Use CloudFront + S3 for static site hosting. Add as a separate future migration step."
}
```

---

### 2g. `private_service` → DEFERRED (out of scope v1)

Add to `deferred[]`:

```json
{
  "service_name": "<name>",
  "service_type": "private_service",
  "plan": "<plan>",
  "reason": "Private services are out of scope in render-to-aws v1.",
  "recommendation": "Use ECS Fargate with internal ALB or AWS App Mesh for private service equivalents."
}
```

---

## Step 3: VPC Design

Determine VPC configuration:

```
IF preferences.network.existing_vpc_id is non-null:
  vpc_design.mode = "existing_vpc"
  vpc_design.existing_vpc_id = preferences.network.existing_vpc_id
  vpc_design.subnet_ids = preferences.network.subnet_ids
ELSE:
  vpc_design.mode = "new_vpc"
  vpc_design.cidr = "10.0.0.0/16"
  vpc_design.subnets = [
    { "az": "<region>a", "cidr": "10.0.1.0/24", "type": "private" },
    { "az": "<region>b", "cidr": "10.0.2.0/24", "type": "private" },
    { "az": "<region>a", "cidr": "10.0.101.0/24", "type": "public" },
    { "az": "<region>b", "cidr": "10.0.102.0/24", "type": "public" }
  ]
```

---

## Step 4: Write aws-design.json

Write `$MIGRATION_DIR/aws-design.json`:

```json
{
  "migration_id": "<from .phase-status.json>",
  "skill": "render-to-aws",
  "phase": "design",
  "timestamp": "<ISO timestamp>",
  "metadata": {
    "total_services": N,
    "compute_target_default": "<preferences.design_constraints.compute_target.default>"
  },
  "services": [ ... ],
  "deferred": [ ... ],
  "warnings": [ ... ],
  "vpc_design": { ... }
}
```

After writing, this file is passed to the `_postconditions` gate in `design.md`. The assembler
is this same file (the mapping engine also serves as assembler for Design — there is no separate
assembler sub-file). Emit `HANDOFF_OK | phase=design` on success.

---

## Scope Boundary

**This sub-file covers Render → AWS mapping ONLY.** Do NOT generate any Terraform, compute cost
estimates, or migration scripts. Those are Phase 5 tasks.
