---
_fragment: terraform
_of_phase: generate
_contributes:
  - terraform/ directory and all .tf files
---

# Generate Phase: Terraform Fragment

> Generates Terraform HCL configurations for all designed AWS services.

**Execute ALL steps in order. Do not skip or deviate.**

---

## Step 1: Core Infrastructure Files

### `terraform/main.tf`

```hcl
terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Environment = var.environment
      ManagedBy   = "Terraform"
      Project     = var.project_name
      MigratedFrom = "Render"
    }
  }
}
```

### `terraform/variables.tf`

Declare at minimum:

- `aws_region` (string, default from `preferences.global.target_region`)
- `environment` (string, default from `preferences.global.environment_naming`)
- `project_name` (string, no default — required)
- Database passwords and secrets as sensitive variables (no defaults for secrets)

### `terraform/outputs.tf`

Declare outputs for:

- Load balancer DNS name / EB endpoint (for web services)
- RDS endpoint and port (if applicable)
- ElastiCache endpoint (if applicable)
- VPC ID and subnet IDs

### `terraform/security.tf`

Security groups for each service layer:

- ALB/EB security group: port 80/443 from 0.0.0.0/0
- Web service security group: port from ALB only
- Background worker security group: no inbound
- RDS security group: port 5432 from web + worker security groups
- ElastiCache security group: port 6379 from web + worker security groups

### `terraform/.gitignore`

```
.terraform/
*.tfstate
*.tfstate.backup
.terraform.lock.hcl
terraform.tfvars
*.tfvars.json
```

### `terraform/terraform.tfvars.example`

Template for required variables (no secret values).

---

## Step 2: VPC / Networking (`terraform/vpc.tf`)

Based on `aws-design.json.vpc_design.mode`:

**`new_vpc`:**

```hcl
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
}
```

Plus subnets, internet gateway, NAT gateway, route tables per the vpc_design subnets array.

**`existing_vpc`:**

Use data sources: `data "aws_vpc" "existing"`, `data "aws_subnet_ids" "private"`.

---

## Step 3: Service-Specific Resources

### Elastic Beanstalk (`terraform/beanstalk.tf`)

Generate for each `aws_service == "Elastic Beanstalk"` entry in `aws-design.json.services[]`:

```hcl
resource "aws_elastic_beanstalk_application" "<name>" {
  name = "<service name>"
}

resource "aws_elastic_beanstalk_environment" "<name>" {
  name                = "<service name>-${var.environment}"
  application         = aws_elastic_beanstalk_application.<name>.name
  solution_stack_name = "64bit Amazon Linux 2023 v4.x.x running Docker"

  setting {
    namespace = "aws:autoscaling:launchconfiguration"
    name      = "InstanceType"
    value     = var.<name>_instance_type
  }
  # ... LoadBalanced environment settings, health check, etc.
}
```

**Deploy method:**

- `github_actions` → `.github/workflows/deploy-eb.yml` (OIDC role assumption)
- `codepipeline` → `terraform/pipeline.tf`
- `manual` → no automation artifact

### ECS Fargate (`terraform/fargate.tf`)

For each `aws_service == "Fargate"`:

```hcl
resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-${var.environment}"
}

resource "aws_ecs_task_definition" "<name>" {
  family                   = "<name>"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "<task_cpu>"
  memory                   = "<task_memory>"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name  = "<name>"
    image = "${aws_ecr_repository.<name>.repository_url}:latest"
    cpu   = <task_cpu>
    memory = <task_memory>
    essential = true
    portMappings = []
  }])
}

resource "aws_ecs_service" "<name>" {
  name            = "<name>-${var.environment}"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.<name>.arn
  desired_count   = <desired_count>
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = [for s in aws_subnet.private : s.id]
    security_groups  = [aws_security_group.<name>.id]
    assign_public_ip = false
  }
}
```

### Lambda + EventBridge Scheduler (`terraform/cron.tf`)

For each `aws_service == "Lambda"` with `scheduler == "EventBridge Scheduler"`:

```hcl
resource "aws_lambda_function" "<name>" {
  function_name = "<name>-${var.environment}"
  role          = aws_iam_role.lambda_<name>.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.<name>.repository_url}:latest"
  memory_size   = <memory_mb>
  timeout       = <timeout_s>
}

resource "aws_scheduler_schedule" "<name>" {
  name       = "<name>-${var.environment}"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression = "cron(<converted from Render cron expression>)"

  target {
    arn      = aws_lambda_function.<name>.arn
    role_arn = aws_iam_role.scheduler_<name>.arn
  }
}
```

### RDS PostgreSQL (`terraform/rds.tf`)

```hcl
resource "aws_db_instance" "<name>" {
  identifier           = "<name>-${var.environment}"
  engine               = "postgres"
  engine_version       = "<version>"
  instance_class       = "<instance_class>"
  allocated_storage    = <storage_gb>
  storage_type         = "gp3"
  username             = var.<name>_db_username
  password             = var.<name>_db_password
  db_subnet_group_name = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  multi_az             = <multi_az>
  skip_final_snapshot  = false
  deletion_protection  = true
}
```

For Aurora (`aws_service == "Aurora PostgreSQL"`): use `aws_rds_cluster` + `aws_rds_cluster_instance`.

### ElastiCache Redis (`terraform/elasticache.tf`)

```hcl
resource "aws_elasticache_cluster" "<name>" {
  cluster_id           = "<name>-${var.environment}"
  engine               = "redis"
  engine_version       = "<engine_version>"
  node_type            = "<node_type>"
  num_cache_nodes      = <num_cache_nodes>
  parameter_group_name = "default.redis7"
  subnet_group_name    = aws_elasticache_subnet_group.main.name
  security_group_ids   = [aws_security_group.elasticache.id]
}
```

For multi-AZ: use `aws_elasticache_replication_group` instead.

---

## Step 4: ECR Repository

For each service that deploys a container (Fargate, Lambda image):

```hcl
resource "aws_ecr_repository" "<name>" {
  name                 = "<name>"
  image_tag_mutability = "MUTABLE"
  force_delete         = false

  image_scanning_configuration {
    scan_on_push = true
  }
}
```

---

## Step 5: Data Migration Script (`scripts/migrate-postgres.sh`)

If postgres is in the design:

```bash
#!/usr/bin/env bash
# migrate-postgres.sh — pg_dump/restore from Render Postgres to RDS
# Generated by render-to-aws skill. Review before running.
set -euo pipefail

RENDER_DB_URL="${RENDER_DB_URL:?RENDER_DB_URL must be set}"
RDS_ENDPOINT="${RDS_ENDPOINT:?RDS_ENDPOINT must be set}"
RDS_DB="${RDS_DB:?RDS_DB must be set}"
RDS_USER="${RDS_USER:?RDS_USER must be set}"

echo "Dumping from Render Postgres..."
pg_dump "$RENDER_DB_URL" --no-owner --no-acl -Fc > /tmp/render-db-dump.pgc

echo "Restoring to RDS..."
pg_restore --host="$RDS_ENDPOINT" --username="$RDS_USER" \
  --dbname="$RDS_DB" --no-owner --no-acl /tmp/render-db-dump.pgc

echo "Migration complete."
```

---

## Step 6: Write `generation-warnings.json`

Record any services that could not be generated (deferred, unsupported, etc.):

```json
{
  "generated": N,
  "deferred": [],
  "warnings": []
}
```
