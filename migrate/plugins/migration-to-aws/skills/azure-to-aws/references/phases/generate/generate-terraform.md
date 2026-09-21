---
_fragment: terraform
_of_phase: generate
_contributes:
  - terraform/main.tf
  - terraform/variables.tf
  - terraform/outputs.tf
  - terraform/security.tf
  - terraform/.gitignore
  - terraform/terraform.tfvars.example
  - scripts/migrate-postgres.sh (conditional on Postgres in design)
---

# Generate Phase: Terraform

Generate AWS Terraform configurations from `aws-design.json`. Output files go to
`$MIGRATION_DIR/terraform/`.

---

## Step 1: main.tf — Provider and Core Resources

```hcl
terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}
```

Then emit one resource block per service in `aws-design.json` services[], following the
patterns below. Use `var.*` references for all configurable values — never hardcode IDs or
names that users must change.

### ECS Fargate Resources

Emit: `aws_ecs_cluster`, `aws_ecs_task_definition`, `aws_ecs_service`, `aws_iam_role`
(task execution role), `aws_security_group` (for the service).

```hcl
resource "aws_ecs_cluster" "main" {
  name = var.app_name
}

resource "aws_ecs_task_definition" "<service_name>" {
  family                   = "<service_name>"
  cpu                      = "<aws_config.task_definition.cpu>"
  memory                   = "<aws_config.task_definition.memory>"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  execution_role_arn       = aws_iam_role.ecs_execution.arn

  container_definitions = jsonencode([{
    name  = "<service_name>"
    image = var.<service_name>_image
    portMappings = [{ containerPort = 8080 }]
  }])
}
```

### Elastic Beanstalk Resources

Emit: `aws_elastic_beanstalk_application`, `aws_elastic_beanstalk_environment`.

### RDS Resources

Emit: `aws_db_instance` with `engine`, `instance_class`, `allocated_storage`, `multi_az`,
`skip_final_snapshot = false`, `deletion_protection = true`.

### S3 Resources

Emit: `aws_s3_bucket`, `aws_s3_bucket_versioning`, `aws_s3_bucket_server_side_encryption_configuration`.

### ElastiCache Resources

Emit: `aws_elasticache_cluster` (single node) or `aws_elasticache_replication_group` (if HA).

### Secrets Manager + KMS Resources

Emit: `aws_kms_key`, `aws_kms_alias`, `aws_secretsmanager_secret` (one per Key Vault).

### Lambda Resources

Emit: `aws_lambda_function`, `aws_iam_role` (lambda execution role), `aws_cloudwatch_log_group`.

### VPC Resources (always emit when new_vpc)

Emit: `aws_vpc`, `aws_subnet` (public + private per AZ), `aws_internet_gateway`,
`aws_route_table`, `aws_route_table_association`.

If HA: emit `aws_nat_gateway` + `aws_eip` per AZ.

---

## Step 2: variables.tf

Declare all variables referenced in main.tf:

```hcl
variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "app_name" {
  description = "Application name prefix for resources"
  type        = string
}

# Per-service image variables, etc.
```

---

## Step 3: outputs.tf

Emit outputs for key resource identifiers (VPC ID, RDS endpoint, ECS cluster ARN, S3
bucket names, etc.).

---

## Step 4: security.tf

Emit security group resources. Separate file for clarity:

- One security group per compute service (ECS tasks, EB environments, Lambda VPC).
- RDS security group allowing ingress from compute SGs only.
- ElastiCache security group allowing ingress from compute SGs only.

---

## Step 5: terraform.tfvars.example

Emit a `terraform.tfvars.example` with all required variable names and placeholder values
(never real secrets):

```hcl
aws_region = "us-east-1"
app_name   = "my-app"
```

---

## Step 6: terraform/.gitignore

```
*.tfstate
*.tfstate.backup
.terraform/
*.tfvars
!terraform.tfvars.example
```

---

## Step 7: scripts/migrate-postgres.sh (conditional)

If `aws-design.json` contains an RDS PostgreSQL service: emit
`$MIGRATION_DIR/scripts/migrate-postgres.sh` — a shell script using `pg_dump` /
`pg_restore` for the data migration cutover:

```bash
#!/usr/bin/env bash
# Azure PostgreSQL → Amazon RDS PostgreSQL data migration
# Requires: psql, pg_dump, pg_restore
set -euo pipefail

AZURE_HOST="${AZURE_POSTGRES_HOST:?Set AZURE_POSTGRES_HOST}"
AWS_HOST="${AWS_RDS_ENDPOINT:?Set AWS_RDS_ENDPOINT}"
DB_NAME="${DB_NAME:?Set DB_NAME}"
DB_USER="${DB_USER:?Set DB_USER}"

echo "Dumping from Azure PostgreSQL..."
pg_dump -h "$AZURE_HOST" -U "$DB_USER" -d "$DB_NAME" -Fc -f /tmp/azure-pg-dump.dump

echo "Restoring to Amazon RDS..."
pg_restore -h "$AWS_HOST" -U "$DB_USER" -d "$DB_NAME" --no-owner /tmp/azure-pg-dump.dump

echo "Migration complete. Verify data integrity before switching connection strings."
```

After generating Terraform files, pass to `generate-assemble.md`. Do NOT update
`.phase-status.json` from this fragment.
