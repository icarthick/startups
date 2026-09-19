---
_fragment: docs
_of_phase: generate
_contributes:
  - MIGRATION_GUIDE.md
  - README.md
---

# Generate Phase: Documentation and Script Generation

> Self-contained sub-file for generating migration documentation and database migration scripts.
> Produces `MIGRATION_GUIDE.md`, `README.md`, and database migration scripts in `$MIGRATION_DIR`.
> Only generates procedures for data stores actually present in the design — omits absent types entirely.

**Execute ALL steps in order. Do not skip or optimize.**

---

## Step 0: Detect Data Store Presence

Scan `aws-design.json`.services[] to determine which compute and data store types exist in the design:

| Check                | Condition                                                                             | Flag                      |
| -------------------- | ------------------------------------------------------------------------------------- | ------------------------- |
| Beanstalk present    | Any service with `aws_service == "Elastic Beanstalk"`                                 | `has_beanstalk = true`    |
| Fargate present      | Any service with `aws_service == "Fargate"` or `aws_service == "ALB"`                 | `has_fargate = true`      |
| Lambda cron present  | Any service with `aws_service == "Lambda"` and source `service_type == "cron_job"`    | `has_lambda_cron = true`  |
| Fargate cron present | Any service with `aws_service == "Fargate Scheduled Task"`                            | `has_fargate_cron = true` |
| Postgres present     | Any service with `aws_service` containing `"RDS PostgreSQL"` or `"Aurora PostgreSQL"` | `has_postgres = true`     |
| Redis present        | Any service with `aws_service == "ElastiCache Redis"`                                 | `has_redis = true`        |

Also extract:

- `deferred_services[]` — entries from `aws-design.json`.deferred[]
- `all_services[]` — full list of designed services for README generation
- `target_region` — from `preferences.json`.global.target_region (default: `us-west-2`)
- `render_services_list` — comma-separated list of unique service names from `render-resource-inventory.json`.resources[]
- `migration_approach` — from `preferences.json`.global.migration_approach (`"full_cutover"` or `"interim_cutover_data_first"`)
- `migration_method` — from `preferences.json`.data.migration_method (`"pg_dump_restore"`, `"dms"`, `"bucardo"`)
- `target_exit_date` — from `preferences.json`.global.target_exit_date (ISO date or null)
- `eb_deploy_method` — from `preferences.json`.design_constraints.eb_deploy_method.value (default: `"github_actions"` when `has_beanstalk` is true)

---

## Step 1: Generate `MIGRATION_GUIDE.md`

Write the migration guide to `$MIGRATION_DIR/MIGRATION_GUIDE.md` using the template below.

**Critical rules:**

- Include a data migration procedure section ONLY for data store types where the corresponding flag is `true`.
- OMIT the entire section (heading and content) for data store types NOT present in the design.
- Include deferred services as manual migration items if any exist.
- Use connection parameter placeholders (never real credentials).

### Template: MIGRATION_GUIDE.md

````markdown
# Migration Guide: Render to AWS

This guide provides step-by-step instructions for migrating your Render application(s) to AWS.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Phase 1: Infrastructure Provisioning](#phase-1-infrastructure-provisioning)
- [Phase 2: Data Migration](#phase-2-data-migration)
- [Phase 3: Application Deployment](#phase-3-application-deployment)
- [Phase 4: Verification](#phase-4-verification)
- [Phase 5: Cutover](#phase-5-cutover)
  {{IF deferred_services.length > 0}}
- [Manual Migration Items](#manual-migration-items)
  {{ENDIF}}

---

## Prerequisites

Before beginning the migration, ensure the following are in place:

### AWS Account Setup

- [ ] AWS account with appropriate IAM permissions for resource creation
- [ ] AWS CLI installed and configured (`aws configure`)
- [ ] Terraform >= 1.5.0 installed
- [ ] Target region selected: `{{target_region}}`

### Render Access

- [ ] Access to Render Dashboard (https://dashboard.render.com) for the services being migrated: {{render_services_list}}
- [ ] Render CLI installed (optional, for live capture reference): `npm install -g @render/cli`
      {{IF has_postgres}}
- [ ] Database credentials for Render Postgres — retrieve from Render Dashboard → your database service → **Connect** tab, or via `render pg info {{render_postgres_service_id}}`
      {{ENDIF}}
      {{IF has_redis}}
- [ ] Redis connection URL from Render Dashboard → your Key Value service → **Connect** tab
      {{ENDIF}}

### Network Requirements

- [ ] VPC and subnet configuration confirmed (see `terraform/` directory)
- [ ] Security group rules reviewed for appropriate access
- [ ] DNS records identified for cutover

### Application Preparation

{{IF has_beanstalk}}

- [ ] Source bundle contains a Dockerfile at the repository root for Elastic Beanstalk Docker deployment
      {{ENDIF}}
      {{IF has_fargate}}
- [ ] Application Docker image built and pushed to ECR (or container registry)
      {{ENDIF}}
- [ ] Environment variables documented and mapped to AWS Secrets Manager / Parameter Store
- [ ] Health check endpoints identified for each web service

{{IF migration_approach == "interim_cutover_data_first"}}

### ⚠️ Interim Operation Advisory

> Your selected migration approach (database first, application stays on Render temporarily) is a **bounded interim phase**. Target exit date: **{{target_exit_date}}**.
>
> Hybrid Render+AWS operation should be limited to weeks, not quarters. Plan your compute migration promptly after data migration completes.
> {{ENDIF}}

---

## Phase 1: Infrastructure Provisioning

Apply the generated Terraform configurations to create AWS resources:

```bash
cd terraform/
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```
````

Verify all resources are created successfully:

```bash
terraform output
```

Record the output values — they are needed for data migration and application deployment.

---

## Phase 2: Data Migration

{{IF has_postgres}}

### PostgreSQL Migration (Render Postgres → RDS/Aurora)

**Strategy:** Use `pg_dump` / `pg_restore` for a full database migration with minimal downtime.

#### Pre-Migration Steps

1. Check current Render Postgres database size from the Render Dashboard → your database service → **Metrics** tab.

2. Suspend Render services to prevent writes during migration (from the Render Dashboard or CLI):

   ```bash
   # Optional: scale web service instances to 0 from Render Dashboard
   # Or use the Render CLI to suspend the service
   render services list
   ```

3. Verify source database size and estimate transfer time by inspecting the Render Dashboard → your database service → **Connect** tab for connection details.

#### Execute Migration

Run the database migration script:

```bash
./scripts/migrate-postgres.sh
```

Or execute manually:

```bash
# Export from Render Postgres
PGPASSWORD="{{SOURCE_DB_PASSWORD}}" pg_dump \
  -h {{SOURCE_DB_HOST}} \
  -p {{SOURCE_DB_PORT}} \
  -U {{SOURCE_DB_USER}} \
  -d {{SOURCE_DB_NAME}} \
  -Fc \
  --no-owner \
  --no-acl \
  --verbose \
  > render_backup.dump

# Import to AWS RDS/Aurora
PGPASSWORD="{{TARGET_DB_PASSWORD}}" pg_restore \
  -h {{TARGET_DB_HOST}} \
  -p {{TARGET_DB_PORT}} \
  -U {{TARGET_DB_USER}} \
  -d {{TARGET_DB_NAME}} \
  --no-owner \
  --no-acl \
  --verbose \
  render_backup.dump
```

#### Post-Migration Verification

```bash
# Connect to target and verify row counts
PGPASSWORD="{{TARGET_DB_PASSWORD}}" psql \
  -h {{TARGET_DB_HOST}} \
  -p {{TARGET_DB_PORT}} \
  -U {{TARGET_DB_USER}} \
  -d {{TARGET_DB_NAME}} \
  -c "SELECT schemaname, relname, n_live_tup FROM pg_stat_user_tables ORDER BY n_live_tup DESC;"
```

Compare row counts between source and target to confirm data integrity.

{{IF migration_approach == "interim_cutover_data_first"}}

#### Interim Database Access (Render Outbound IPs → Scoped Allowlist)

During the interim period your Render application connects to the AWS database. Complete these steps **in order** — TLS must be enforced before any network path is opened.

> **⚠️ Never open port 5432 to `0.0.0.0/0`.** Render services egress from a known set of outbound IPs — use those as a bounded, enumerated allowlist. A world-reachable database port is exposed to internet-wide scanning and credential stuffing regardless of TLS.

##### Step 1 — Enforce TLS on the database (prerequisite gate)

The generated Terraform already sets `rds.force_ssl = 1` for this database. After `terraform apply`:

- **RDS for PostgreSQL** — the parameter is **static**; reboot the instance once so it takes effect:

  ```bash
  aws rds reboot-db-instance --db-instance-identifier <db_identifier>
  ```

- **Aurora PostgreSQL** — the parameter is **dynamic** at the cluster level; no reboot is needed.

Verify enforcement before opening any network path:

```bash
# (a) pg_hba rules must be hostssl, not host
psql "$ADMIN_DATABASE_URL" -c "SELECT type, database, auth_method FROM pg_hba_file_rules;"

# (b) a plaintext connection must be REJECTED
psql "postgres://{{TARGET_DB_USER}}@{{TARGET_DB_HOST}}:{{TARGET_DB_PORT}}/{{TARGET_DB_NAME}}?sslmode=disable"
# Expected: FATAL: no pg_hba.conf entry ... SSL off
```

If (a) shows `host` instead of `hostssl`, or (b) succeeds, **stop here** — TLS is not in effect. Do not open any network path until both checks pass.

##### Step 2 — Retrieve Render service outbound IPs

Every Render service egresses from a small, stable set of outbound IP addresses. Find them in the Render Dashboard:

- Open the **Dashboard** → navigate to your web service → **Settings** → scroll to **Outbound IPs**.
- Note all listed IPs (typically 2–4 addresses). These are per-region and stable unless you change regions.

Alternatively, Render publishes its IP ranges in the documentation at https://render.com/docs/static-outbound-ip-addresses.

**Allowlist:** each outbound IP as a `/32`. Never use `0.0.0.0/0`.

##### Step 3 — Apply the allowlist via Terraform (not the console)

Make every interim change in the generated Terraform and commit it:

In `terraform/terraform.tfvars`, set the interim variables the generator emits, then plan and apply:

```hcl
interim_render_ingress_cidrs = ["203.0.113.10/32", "203.0.113.11/32"] # from Step 2
interim_db_public_access     = true                                    # required: RDS must be publicly accessible for Render to reach it
```

```bash
terraform plan -out=tfplan   # review the single added ingress rule before applying
terraform apply tfplan
```

`interim_render_ingress_cidrs` defaults to `[]` (no ingress rule). It rejects `0.0.0.0/0`. `interim_db_public_access` defaults to `false` — set `true` only for this interim period.

> **Note:** making RDS publicly accessible sends traffic over the public internet. This is acceptable only with TLS enforced (Step 1) and a bounded IP allowlist (Step 2/3). Keep the interim period short.

##### Step 4 — Update DATABASE_URL in Render

Point your Render service's `DATABASE_URL` environment variable to the AWS RDS endpoint:

From the Render Dashboard → your web service → **Environment** → update `DATABASE_URL`:

```
postgres://{{TARGET_DB_USER}}:{{TARGET_DB_PASSWORD}}@{{TARGET_DB_HOST}}:{{TARGET_DB_PORT}}/{{TARGET_DB_NAME}}?sslmode=verify-full
```

Add the RDS CA bundle to your repository and reference it with `sslrootcert` if your application client requires certificate verification beyond hostname validation.

##### Step 5 — Close the interim path at cutover

Once the application runs on AWS and no longer connects from Render:

1. Reset both variables to defaults (`interim_render_ingress_cidrs = []`, `interim_db_public_access = false`), then `terraform apply`. Confirm the plan removes the ingress rule.
2. Delete the interim variables and the gated ingress block from the Terraform.
3. Confirm the application reaches the database over private VPC networking only, and that the database reports `Not publicly accessible`.
   {{ENDIF}}

{{IF migration_method == "dms"}}

#### Alternative: AWS DMS Bulk Migration

For databases over ~10GB, AWS DMS can provide a faster migration with less downtime:

⚠️ **Important limitation:** AWS DMS **cannot** perform continuous replication (CDC) with Render Postgres. Render does not grant the `REPLICATION` role required for logical replication slots. DMS is for **one-time bulk data migration** with a final cutover window only. Verify whether Render grants this role for your plan tier before committing to this path.

**DMS Setup Steps:**

1. Create a DMS replication instance (publicly accessible, same VPC as target RDS)
2. Create source endpoint pointing to Render Postgres (SSL mode: require)
3. Create target endpoint pointing to your AWS RDS/Aurora instance
4. Copy schema first: `pg_dump --schema-only` from Render → `pg_restore` to target
5. Create migration task with:
   - Migration type: "Migrate existing data" (NOT "Replicate data changes")
   - Target table prep mode: "Do nothing" (schema already copied)
   - LOB mode: "Full LOB mode"
6. Enable pre-migration assessment and review results
7. Start the migration task
8. After completion, perform final cutover using the Render cutover sequence below
   {{ENDIF}}

{{IF migration_method == "bucardo"}}

#### Alternative: Bucardo (Near-Zero Downtime)

For near-zero downtime migration using trigger-based replication:

**Requirements:**

- Dedicated EC2 instance (Ubuntu 20.04+) to run Bucardo
- PostgreSQL client matching source version
- Ability to create triggers on the Render Postgres database
- Primary keys on all source tables

**Setup overview:** Bucardo performs an initial full copy, then switches to delta-push mode for continuous replication until cutover. See the detailed Bucardo setup procedure in your migration reference documentation.

**Note:** Bucardo does not support LOB migration. Stored functions/procedures must be migrated separately via `pg_dump --schema-only`.
{{ENDIF}}

#### Render Cutover Sequence

Regardless of migration method, the final cutover follows this sequence:

```bash
# 1. Suspend Render services (prevents new writes)
#    From Render Dashboard: scale instances to 0 for each service, or suspend the service

# 2. Final backup (safety net)
PGPASSWORD="{{SOURCE_DB_PASSWORD}}" pg_dump \
  -h {{SOURCE_DB_HOST}} -p {{SOURCE_DB_PORT}} \
  -U {{SOURCE_DB_USER}} -d {{SOURCE_DB_NAME}} \
  -Fc --no-owner --no-acl \
  -f render_final_backup_$(date +%Y%m%d_%H%M%S).dump

# 3. If using pg_dump: run final migration now
# If using DMS/Bucardo: wait for final sync, then stop replication

# 4. Verify data in target database (row counts, spot checks)

# 5. Deploy application to AWS (Phase 3 below)

# 6. Resume Render services only if rollback is needed
```

**After full application migration to AWS (no longer on Render):**

```bash
# Confirm application is healthy on AWS, then proceed to Phase 5 to decommission Render
```

{{ENDIF}}
{{IF has_redis}}

### Redis Migration (Render Key Value → ElastiCache)

**Strategy:** Export Redis data using `DUMP`/`RESTORE` or `redis-cli --rdb` depending on dataset size.

#### Pre-Migration Steps

1. Check current Redis memory usage and key count from the Render Dashboard → your Key Value service → **Metrics** tab.

2. Retrieve connection details from Render Dashboard → your Key Value service → **Connect** tab.

3. Determine migration approach:
   - **Small dataset (< 1 GB):** Use key-by-key `DUMP`/`RESTORE`
   - **Large dataset (≥ 1 GB):** Use RDB snapshot transfer

#### Execute Migration (Small Dataset)

```bash
./scripts/migrate-redis.sh
```

Or execute manually using `redis-cli`:

```bash
# Connect to source and dump keys
redis-cli -h {{SOURCE_REDIS_HOST}} -p {{SOURCE_REDIS_PORT}} \
  -a "{{SOURCE_REDIS_PASSWORD}}" --tls \
  --scan --pattern '*' | while read key; do
    redis-cli -h {{SOURCE_REDIS_HOST}} -p {{SOURCE_REDIS_PORT}} \
      -a "{{SOURCE_REDIS_PASSWORD}}" --tls \
      DUMP "$key" | redis-cli -h {{TARGET_REDIS_HOST}} -p {{TARGET_REDIS_PORT}} \
      -a "{{TARGET_REDIS_PASSWORD}}" --tls \
      RESTORE "$key" 0 -
done
```

#### Execute Migration (Large Dataset)

```bash
# Generate RDB snapshot from source
redis-cli -h {{SOURCE_REDIS_HOST}} -p {{SOURCE_REDIS_PORT}} \
  -a "{{SOURCE_REDIS_PASSWORD}}" --tls \
  --rdb render_redis.rdb

# Import to ElastiCache (use S3 as intermediary)
aws s3 cp render_redis.rdb s3://{{MIGRATION_BUCKET}}/redis/render_redis.rdb
# Then use ElastiCache seed-from-S3 or restore from backup
```

#### Post-Migration Verification

```bash
# Compare key counts
echo "Source keys:" && redis-cli -h {{SOURCE_REDIS_HOST}} -p {{SOURCE_REDIS_PORT}} \
  -a "{{SOURCE_REDIS_PASSWORD}}" --tls DBSIZE
echo "Target keys:" && redis-cli -h {{TARGET_REDIS_HOST}} -p {{TARGET_REDIS_PORT}} \
  -a "{{TARGET_REDIS_PASSWORD}}" --tls DBSIZE
```

{{ENDIF}}

---

## Phase 3: Application Deployment

{{IF has_beanstalk}}

### Deploy to Elastic Beanstalk

The generated EB path deploys a source bundle containing your Dockerfile. GitHub Actions is the default deploy mechanism; CodePipeline is available only when selected during Clarify.

{{IF eb_deploy_method == "github_actions"}}

### GitHub Actions Deploy (Default)

The generated `.github/workflows/deploy-eb.yml` workflow uses GitHub OIDC role assumption, packages the source bundle, creates an Elastic Beanstalk application version, and updates each generated EB environment.

Before first run, create or provide a GitHub OIDC IAM role with permissions to call `elasticbeanstalk create-storage-location`, `elasticbeanstalk create-application-version`, `elasticbeanstalk update-environment`, and upload the source bundle to the EB storage bucket. Store the role ARN as the repository secret `AWS_ROLE_ARN`.

{{ENDIF}}
{{IF eb_deploy_method == "codepipeline"}}

### CodePipeline Deploy

The generated `terraform/pipeline.tf` creates an AWS-managed CodePipeline path from GitHub to Elastic Beanstalk. Complete the one-time GitHub connection authorization in the AWS console before expecting push-triggered deployments to run.

{{ENDIF}}
{{IF eb_deploy_method == "manual"}}

### Manual EB CLI Deploy

No automated deploy artifact was generated. Package and deploy manually:

```bash
VERSION_LABEL="v$(date +%Y%m%d%H%M%S)"
BUCKET="$(aws elasticbeanstalk create-storage-location --query S3Bucket --output text --region {{target_region}})"
zip -r app.zip . -x '.git/*' 'node_modules/*'
aws s3 cp app.zip "s3://${BUCKET}/{{app_name}}/${VERSION_LABEL}.zip" --region {{target_region}}
aws elasticbeanstalk create-application-version \
  --application-name {{app_name}} \
  --version-label "${VERSION_LABEL}" \
  --source-bundle "S3Bucket=${BUCKET},S3Key={{app_name}}/${VERSION_LABEL}.zip" \
  --region {{target_region}}
for ENVIRONMENT in {{EB_ENVIRONMENT_NAMES}}; do
  aws elasticbeanstalk update-environment \
    --environment-name "${ENVIRONMENT}" \
    --version-label "${VERSION_LABEL}" \
    --region {{target_region}}
done
```

{{ENDIF}}

### EB Config Var Migration

Export all Render environment variables from the Render Dashboard → your service → **Environment** tab and import sensitive values to AWS Secrets Manager or SSM Parameter Store. Reference secrets in EB via the `environmentsecrets` namespace configured in `beanstalk.tf`; set non-sensitive config directly as EB environment properties.

{{ENDIF}}
{{IF has_fargate}}

### Build and Push Container Image

```bash
# Build Docker image
docker build -t {{app_name}}:latest .

# Tag for ECR
docker tag {{app_name}}:latest {{AWS_ACCOUNT_ID}}.dkr.ecr.{{target_region}}.amazonaws.com/{{app_name}}:latest

# Push to ECR
aws ecr get-login-password --region {{target_region}} | docker login --username AWS --password-stdin {{AWS_ACCOUNT_ID}}.dkr.ecr.{{target_region}}.amazonaws.com
docker push {{AWS_ACCOUNT_ID}}.dkr.ecr.{{target_region}}.amazonaws.com/{{app_name}}:latest
```

### Deploy to Fargate

The Terraform configuration creates ECS services automatically. After pushing the image, force a new deployment:

```bash
aws ecs update-service \
  --cluster {{app_name}}-cluster \
  --service {{app_name}}-web \
  --force-new-deployment \
  --region {{target_region}}
```

### Fargate Config Var Migration

Export all Render environment variables from the Render Dashboard → your service → **Environment** tab and import to AWS Secrets Manager / Parameter Store, then reference them in your ECS task definition.

{{ENDIF}}
{{IF has_lambda_cron}}

### Cron Jobs — Lambda + EventBridge

The Terraform configuration provisions Lambda functions and EventBridge Scheduler rules for each cron job mapped to Lambda. After Terraform apply, deploy the Lambda function code:

```bash
# Package and deploy Lambda function for each cron job
zip -r function.zip . -x '.git/*'
aws lambda update-function-code \
  --function-name {{lambda_function_name}} \
  --zip-file fileb://function.zip \
  --region {{target_region}}
```

Verify the EventBridge schedule rule is enabled and the Lambda function is configured with the correct environment variables from AWS Secrets Manager / Parameter Store.

{{ENDIF}}
{{IF has_fargate_cron}}

### Cron Jobs — Fargate Scheduled Tasks

The Terraform configuration provisions ECS Fargate task definitions and EventBridge Scheduler rules for cron jobs mapped to Fargate Scheduled Tasks. After Terraform apply and container image push:

```bash
aws ecs describe-task-definition \
  --task-definition {{cron_task_definition_name}} \
  --region {{target_region}}
```

Verify that the scheduled rule is enabled in EventBridge and that environment variables are sourced from Secrets Manager / Parameter Store.

{{ENDIF}}

## Phase 4: Verification

### Health Checks

{{IF has_beanstalk}}

- [ ] Application responds on EB environment URL: `http://{{EB_ENVIRONMENT_URL}}/`
- [ ] Health check endpoint returns 200: `http://{{EB_ENVIRONMENT_URL}}/health`
      {{ENDIF}}
      {{IF has_fargate}}
- [ ] Application responds on ALB endpoint: `https://{{ALB_DNS_NAME}}/`
- [ ] Health check endpoint returns 200: `https://{{ALB_DNS_NAME}}/health`
      {{ENDIF}}
      {{IF has_postgres}}
- [ ] Database connectivity confirmed (application can read/write)
- [ ] Row counts match source database
      {{ENDIF}}
      {{IF has_redis}}
- [ ] Redis connectivity confirmed (application can read/write cache)
- [ ] Key counts match source Redis
      {{ENDIF}}
      {{IF has_lambda_cron}}
- [ ] Lambda cron functions invoked successfully (check CloudWatch Logs)
- [ ] EventBridge Scheduler rules are enabled and firing on schedule
      {{ENDIF}}
      {{IF has_fargate_cron}}
- [ ] Fargate Scheduled Tasks completing successfully (check ECS task history)
- [ ] EventBridge Scheduler rules are enabled and firing on schedule
      {{ENDIF}}

### Functional Tests

- [ ] Run application test suite against AWS deployment
- [ ] Verify critical user flows end-to-end
- [ ] Check log output in CloudWatch Logs

### Performance Baseline

- [ ] Response time within acceptable range (compare to Render baseline)
- [ ] No error rate increase in CloudWatch metrics
- [ ] Resource utilization (CPU/memory) within expected bounds

---

## Phase 5: Cutover

### DNS Cutover

1. Update DNS records to point at the active AWS endpoint:

{{IF has_beanstalk}}

```
{{app_domain}} → CNAME → {{EB_ENVIRONMENT_URL}}
```

{{ENDIF}}
{{IF has_fargate}}

```
{{app_domain}} → CNAME → {{ALB_DNS_NAME}}
```

{{ENDIF}}

2. Set TTL low (60s) before cutover, restore after verification.

### Post-Migration Lockdown

Once your application is fully running on AWS (no longer connecting from Render):

- [ ] **Disable public access on RDS/Aurora:** Confirm the database reports "Not publicly accessible"
- [ ] **Restrict security groups:** Ensure no `0.0.0.0/0` inbound rules remain; allow only VPC-internal traffic on database ports
- [ ] **Verify backups:** Confirm automated backups are enabled with appropriate retention
- [ ] **Confirm private connectivity:** Application connects to the database via private VPC networking (not public endpoint)

{{IF migration_approach == "interim_cutover_data_first"}}

- [ ] **Close the interim access path in Terraform:** reset `interim_render_ingress_cidrs = []` and `interim_db_public_access = false`, `terraform apply`, then delete the interim ingress block — full procedure in "Interim Database Access" Step 5 above

{{ENDIF}}

### Decommission Render Services

After successful verification (recommend 48–72 hours of parallel running):

1. Suspend Render services from the Dashboard (set instances to 0 or suspend each service):

   From **Render Dashboard** → each service → **Settings** → **Suspend Service**

2. After confirming all traffic and data is on AWS, delete services:

   From **Render Dashboard** → each service → **Settings** → **Delete Service**

   ⚠️ Deletion is irreversible. Only delete after confirming all data is accessible in AWS and the application is stable.

{{IF deferred_services.length > 0}}

---

## Manual Migration Items

The following Render service types could not be automatically mapped to AWS equivalents and require manual migration:

| Service | Type | Reason | Recommendation |
| ------- | ---- | ------ | -------------- |

<!-- markdownlint-disable MD055 MD056 -->

{{FOR svc IN deferred_services}}
| {{svc.service_name}} | {{svc.service_type}} | {{svc.reason}} | {{svc.recommendation}} |
{{ENDFOR}}

<!-- markdownlint-enable MD055 MD056 -->

### Action Required

For each deferred service above:

1. Identify the equivalent AWS service or third-party replacement
2. Provision the replacement service manually
3. Migrate data/configuration from the Render service
4. Update application configuration to use the new service endpoint
5. Verify functionality before decommissioning the Render service

{{ENDIF}}

````
### Template Variable Resolution

Replace template variables using these sources:

| Variable | Source |
|----------|--------|
| `{{target_region}}` | `preferences.json` → `global.target_region` |
| `{{app_name}}` | Primary service name from `render-resource-inventory.json`.resources[] |
| `{{render_services_list}}` | All service names from `render-resource-inventory.json`.resources[], comma-separated |
| `{{render_postgres_service_id}}` | `service_id` of the postgres service from `render-resource-inventory.json` |
| `{{migration_approach}}` | `preferences.json` → `global.migration_approach` |
| `{{migration_method}}` | `preferences.json` → `data.migration_method` |
| `{{target_exit_date}}` | `preferences.json` → `global.target_exit_date` (or "not set") |
| `{{SOURCE_DB_*}}` | Placeholder — user fills from Render Dashboard → database service → Connect tab |
| `{{TARGET_DB_*}}` | Placeholder — user fills from Terraform output |
| `{{SOURCE_REDIS_*}}` | Placeholder — user fills from Render Dashboard → Key Value service → Connect tab |
| `{{TARGET_REDIS_*}}` | Placeholder — user fills from Terraform output |
| `{{AWS_ACCOUNT_ID}}` | Placeholder — user fills with their AWS account ID |
| `{{ALB_DNS_NAME}}` | Placeholder — user fills from Terraform output |
| `{{EB_ENVIRONMENT_URL}}` | Elastic Beanstalk web environment CNAME output |
| `{{EB_ENVIRONMENT_NAMES}}` | Space-separated generated Elastic Beanstalk environment names for all EB process types |
| `{{lambda_function_name}}` | Generated Lambda function name from Terraform output |
| `{{cron_task_definition_name}}` | Generated ECS task definition name for Fargate cron from Terraform output |
| `{{MIGRATION_BUCKET}}` | Placeholder — user creates an S3 bucket for migration artifacts |
| `{{app_domain}}` | Placeholder — user fills with their application domain |

### Conditional Section Rules

**Strict enforcement — no empty sections:**

- If `has_postgres == false`: Omit the entire "PostgreSQL Migration" subsection under Phase 2 (heading + content)
- If `has_redis == false`: Omit the entire "Redis Migration" subsection under Phase 2 (heading + content)
- If ALL data store flags are false: Omit the entire "Phase 2: Data Migration" section and its Table of Contents entry
- If `deferred_services.length == 0`: Omit the entire "Manual Migration Items" section and its Table of Contents entry
- If `has_lambda_cron == false`: Omit the Lambda cron deployment section in Phase 3
- If `has_fargate_cron == false`: Omit the Fargate Scheduled Tasks deployment section in Phase 3
- Verification section (Phase 4) checkboxes: Only include data-store-specific and compute-specific checks for present types

---

## Step 2: Generate `README.md`

Write the README to `$MIGRATION_DIR/README.md` listing all generated artifacts.

### Template: README.md

```markdown
# Render-to-AWS Migration Artifacts

Generated by the render-to-aws migration skill on {{generation_timestamp}}.

## Overview

This directory contains all artifacts needed to migrate your Render application(s) to AWS.

**Source:** {{render_services_list}} (Render)
**Target:** AWS ({{target_region}})
**Estimated Monthly Cost:** ${{estimated_monthly_total}} USD

---

## Artifact Files

| File | Purpose |
|------|---------|
| `terraform/` | Terraform configurations for all AWS infrastructure |
| `terraform/main.tf` | Provider configuration and module declarations |
| `terraform/variables.tf` | Input variables (region, VPC, naming) |
| `terraform/outputs.tf` | Output values (endpoints, ARNs, DNS names) |
{{IF has_beanstalk}}
| `terraform/beanstalk.tf` | Elastic Beanstalk applications and environments |
{{IF eb_deploy_method == "github_actions"}}
| `.github/workflows/deploy-eb.yml` | GitHub Actions source-to-EB deploy workflow |
{{ENDIF}}
{{IF eb_deploy_method == "codepipeline"}}
| `terraform/pipeline.tf` | Optional CodePipeline source-to-EB deploy path |
{{ENDIF}}
{{ENDIF}}
{{IF has_fargate}}
| `terraform/ecs.tf` | ECS/Fargate task definitions and services |
| `terraform/alb.tf` | Application Load Balancer configuration |
{{ENDIF}}
{{IF has_lambda_cron}}
| `terraform/cron.tf` | Lambda + EventBridge Scheduler for cron jobs |
{{ENDIF}}
{{IF has_fargate_cron}}
| `terraform/fargate.tf` | Fargate Scheduled Tasks for cron jobs (if not already present) |
{{ENDIF}}
{{IF has_postgres}}
| `terraform/rds.tf` | RDS/Aurora PostgreSQL database configuration |
{{ENDIF}}
{{IF has_redis}}
| `terraform/elasticache.tf` | ElastiCache Redis cluster configuration |
{{ENDIF}}
| `terraform/vpc.tf` | VPC, subnets, and networking configuration |
| `terraform/security-groups.tf` | Security group rules |
| `MIGRATION_GUIDE.md` | Step-by-step migration procedure |
| `README.md` | This file — artifact listing and quick start |
| `migration-report.html` | Stakeholder summary (costs + optional what-if scenarios); draft for review |
{{IF has_postgres}}
| `scripts/migrate-postgres.sh` | PostgreSQL data migration script |
{{ENDIF}}
{{IF has_redis}}
| `scripts/migrate-redis.sh` | Redis data migration script |
{{ENDIF}}
{{IF generation_warnings_exist}}
| `generation-warnings.json` | Resources that could not be generated |
{{ENDIF}}
| `.phase-status.json` | Migration phase tracking (internal) |
| `render-resource-inventory.json` | Discovered Render resources (input) |
| `preferences.json` | Migration preferences (input) |
| `aws-design.json` | Designed AWS architecture (input) |
| `estimation-infra.json` | Cost estimates (input) |
| `scenarios/` | Optional what-if workshop snapshots (baseline + priced variants; see skill workshop docs) |

> **SA tip:** After Estimate (before or instead of regenerating), you can re-enter
> what-if workshop mode to change region, HA, compute target, or Graviton
> preference and compare up to 5 scenarios without re-discovery. Generated
> `migration-report.html` includes the scenario comparison when variants exist.

---

## Quick Start

### 1. Review the Migration Guide

Read `MIGRATION_GUIDE.md` for the complete migration procedure including prerequisites, data migration steps, and verification.

### 2. Configure Variables

Edit `terraform/variables.tf` or create a `terraform.tfvars` file:

```hcl
aws_region     = "{{target_region}}"
environment    = "{{environment_name}}"
# Add VPC, subnet, and other variables as needed
````

### 3. Apply Terraform

```bash
cd terraform/

# Initialize providers and modules
terraform init

# Preview changes
terraform plan -out=tfplan

# Apply infrastructure
terraform apply tfplan

# Record outputs for data migration
terraform output > ../terraform-outputs.txt
```

### 4. Migrate Data

{{IF has_postgres}}

```bash
# Migrate PostgreSQL database
./scripts/migrate-postgres.sh
```

{{ENDIF}}
{{IF has_redis}}

```bash
# Migrate Redis data
./scripts/migrate-redis.sh
```

{{ENDIF}}

### 5. Deploy Application

{{IF has_beanstalk}}
Deploy through the selected Elastic Beanstalk deploy method from `MIGRATION_GUIDE.md` Phase 3. The default is the generated GitHub Actions workflow.
{{ENDIF}}
{{IF has_fargate}}
Build and push your container image, then update ECS services. See `MIGRATION_GUIDE.md` Phase 3 for details.
{{ENDIF}}

### 6. Verify and Cutover

Follow the verification checklist in `MIGRATION_GUIDE.md` Phase 4, then perform DNS cutover per Phase 5.

---

## Important Notes

- **Placeholders:** Connection strings and credentials use `{{PLACEHOLDER}}` format. Replace with actual values from Render Dashboard (Connect tab) and Terraform outputs.
- **Order matters:** Apply Terraform BEFORE running data migration scripts. The target infrastructure must exist first.
- **Backup:** Always verify backups exist before performing destructive operations on Render services.
- **Parallel run:** Recommended 48–72 hours of parallel running before decommissioning Render services.
  {{IF deferred_services.length > 0}}
- **Manual items:** {{deferred_services.length}} service(s) require manual migration. See "Manual Migration Items" in `MIGRATION_GUIDE.md`.
  {{ENDIF}}

````
### Template Variable Resolution

| Variable | Source |
|----------|--------|
| `{{generation_timestamp}}` | Current ISO 8601 timestamp |
| `{{render_services_list}}` | All service names from `render-resource-inventory.json`.resources[] |
| `{{target_region}}` | `preferences.json` → `global.target_region` |
| `{{estimated_monthly_total}}` | `estimation-infra.json` → total projected monthly cost |
| `{{environment_name}}` | `preferences.json` → `global.environment_naming` |
| `{{deferred_services.length}}` | Count of entries in `aws-design.json`.deferred[] |

### Conditional Section Rules

- `has_beanstalk`: True if any service in design has `aws_service == "Elastic Beanstalk"`
- `eb_deploy_method`: `preferences.design_constraints.eb_deploy_method.value`; default to `"github_actions"` when absent and `has_beanstalk` is true
- `has_fargate`: True if any service in design has `aws_service == "Fargate"` or `aws_service == "ALB"`
- `has_lambda_cron`: True if any service in design has `aws_service == "Lambda"` with source `service_type == "cron_job"`
- `has_fargate_cron`: True if any service in design has `aws_service == "Fargate Scheduled Task"`
- `has_postgres`: True if any service has `aws_service` containing `"RDS PostgreSQL"` or `"Aurora PostgreSQL"`
- `has_redis`: True if any service has `aws_service == "ElastiCache Redis"`
- `generation_warnings_exist`: True if `generation-warnings.json` has a NON-EMPTY `warnings` array (the file is always written, so test its contents, not its existence)

---

## Step 3: Generate Database Migration Scripts

Generate migration scripts ONLY for data stores present in the design. Place scripts in `$MIGRATION_DIR/scripts/`.

### 3A: PostgreSQL Migration Script

**Trigger:** `has_postgres == true`

Write to `$MIGRATION_DIR/scripts/migrate-postgres.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# PostgreSQL Migration Script
# Migrates data from Render Postgres to AWS RDS/Aurora PostgreSQL
#
# Prerequisites:
#   - pg_dump and pg_restore installed (PostgreSQL client tools)
#   - Network access to both source and target databases
#   - Source and target credentials configured below
#
# Usage:
#   1. Fill in connection parameters below (source: Render Dashboard → Connect tab)
#   2. Run: chmod +x migrate-postgres.sh && ./migrate-postgres.sh
###############################################################################

# ─── Source Connection (Render Postgres) ─────────────────────────────────────
# Retrieve via: Render Dashboard → your database service → Connect tab
SOURCE_DB_HOST="{{SOURCE_DB_HOST}}"
SOURCE_DB_PORT="{{SOURCE_DB_PORT}}"
SOURCE_DB_USER="{{SOURCE_DB_USER}}"
SOURCE_DB_PASSWORD="{{SOURCE_DB_PASSWORD}}"
SOURCE_DB_NAME="{{SOURCE_DB_NAME}}"

# ─── Target Connection (AWS RDS/Aurora) ──────────────────────────────────────
# Retrieve via: terraform output (after terraform apply)
TARGET_DB_HOST="{{TARGET_DB_HOST}}"
TARGET_DB_PORT="{{TARGET_DB_PORT}}"
TARGET_DB_USER="{{TARGET_DB_USER}}"
TARGET_DB_PASSWORD="{{TARGET_DB_PASSWORD}}"
TARGET_DB_NAME="{{TARGET_DB_NAME}}"

# ─── Configuration ───────────────────────────────────────────────────────────
BACKUP_FILE="render_postgres_backup_$(date +%Y%m%d_%H%M%S).dump"
LOG_FILE="postgres_migration_$(date +%Y%m%d_%H%M%S).log"

# ─── Functions ───────────────────────────────────────────────────────────────
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

check_prerequisites() {
  log "Checking prerequisites..."
  command -v pg_dump >/dev/null 2>&1 || { log "ERROR: pg_dump not found"; exit 1; }
  command -v pg_restore >/dev/null 2>&1 || { log "ERROR: pg_restore not found"; exit 1; }
  command -v psql >/dev/null 2>&1 || { log "ERROR: psql not found"; exit 1; }
  log "Prerequisites OK"
}

test_source_connection() {
  log "Testing source database connection (Render Postgres)..."
  PGPASSWORD="$SOURCE_DB_PASSWORD" psql \
    -h "$SOURCE_DB_HOST" -p "$SOURCE_DB_PORT" \
    -U "$SOURCE_DB_USER" -d "$SOURCE_DB_NAME" \
    -c "SELECT 1;" >/dev/null 2>&1 || { log "ERROR: Cannot connect to source database"; exit 1; }
  log "Source connection OK"
}

test_target_connection() {
  log "Testing target database connection (AWS RDS/Aurora)..."
  PGPASSWORD="$TARGET_DB_PASSWORD" psql \
    -h "$TARGET_DB_HOST" -p "$TARGET_DB_PORT" \
    -U "$TARGET_DB_USER" -d "$TARGET_DB_NAME" \
    -c "SELECT 1;" >/dev/null 2>&1 || { log "ERROR: Cannot connect to target database"; exit 1; }
  log "Target connection OK"
}

export_source() {
  log "Exporting source database to $BACKUP_FILE..."
  PGPASSWORD="$SOURCE_DB_PASSWORD" pg_dump \
    -h "$SOURCE_DB_HOST" \
    -p "$SOURCE_DB_PORT" \
    -U "$SOURCE_DB_USER" \
    -d "$SOURCE_DB_NAME" \
    -Fc \
    --no-owner \
    --no-acl \
    --verbose \
    -f "$BACKUP_FILE" 2>>"$LOG_FILE"
  log "Export complete: $(du -h "$BACKUP_FILE" | cut -f1)"
}

import_target() {
  log "Importing to target database..."
  PGPASSWORD="$TARGET_DB_PASSWORD" pg_restore \
    -h "$TARGET_DB_HOST" \
    -p "$TARGET_DB_PORT" \
    -U "$TARGET_DB_USER" \
    -d "$TARGET_DB_NAME" \
    --no-owner \
    --no-acl \
    --verbose \
    "$BACKUP_FILE" 2>>"$LOG_FILE"
  log "Import complete"
}

verify_migration() {
  log "Verifying migration..."

  SOURCE_COUNT=$(PGPASSWORD="$SOURCE_DB_PASSWORD" psql \
    -h "$SOURCE_DB_HOST" -p "$SOURCE_DB_PORT" \
    -U "$SOURCE_DB_USER" -d "$SOURCE_DB_NAME" \
    -t -c "SELECT SUM(n_live_tup) FROM pg_stat_user_tables;" | tr -d ' ')

  TARGET_COUNT=$(PGPASSWORD="$TARGET_DB_PASSWORD" psql \
    -h "$TARGET_DB_HOST" -p "$TARGET_DB_PORT" \
    -U "$TARGET_DB_USER" -d "$TARGET_DB_NAME" \
    -t -c "SELECT SUM(n_live_tup) FROM pg_stat_user_tables;" | tr -d ' ')

  log "Source row count: $SOURCE_COUNT"
  log "Target row count: $TARGET_COUNT"

  if [ "$SOURCE_COUNT" == "$TARGET_COUNT" ]; then
    log "Row counts match — migration verified"
  else
    log "WARNING: Row count mismatch (source=$SOURCE_COUNT, target=$TARGET_COUNT)"
    log "  This may be expected if the source had writes during migration."
    log "  Review per-table counts to identify discrepancies."
  fi
}

# ─── Main ────────────────────────────────────────────────────────────────────
main() {
  log "=== PostgreSQL Migration Started (Render Postgres -> AWS RDS/Aurora) ==="
  check_prerequisites
  test_source_connection
  test_target_connection
  export_source
  import_target
  verify_migration
  log "=== PostgreSQL Migration Complete ==="
  log "Backup file: $BACKUP_FILE"
  log "Log file: $LOG_FILE"
}

main "$@"
````

### 3B: Redis Migration Script

**Trigger:** `has_redis == true`

Write to `$MIGRATION_DIR/scripts/migrate-redis.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# Redis Migration Script
# Migrates data from Render Key Value (Redis) to AWS ElastiCache Redis
#
# Prerequisites:
#   - redis-cli installed (Redis client tools)
#   - Network access to both source and target Redis instances
#   - TLS support enabled in redis-cli (if source/target use TLS)
#
# Usage:
#   1. Fill in connection parameters below (source: Render Dashboard → Connect tab)
#   2. Run: chmod +x migrate-redis.sh && ./migrate-redis.sh
###############################################################################

# ─── Source Connection (Render Key Value / Redis) ────────────────────────────
# Retrieve via: Render Dashboard → your Key Value service → Connect tab
SOURCE_REDIS_HOST="{{SOURCE_REDIS_HOST}}"
SOURCE_REDIS_PORT="{{SOURCE_REDIS_PORT}}"
SOURCE_REDIS_PASSWORD="{{SOURCE_REDIS_PASSWORD}}"
SOURCE_REDIS_TLS="true"

# ─── Target Connection (AWS ElastiCache) ─────────────────────────────────────
# Retrieve via: terraform output (after terraform apply)
TARGET_REDIS_HOST="{{TARGET_REDIS_HOST}}"
TARGET_REDIS_PORT="{{TARGET_REDIS_PORT}}"
TARGET_REDIS_PASSWORD="{{TARGET_REDIS_PASSWORD}}"
TARGET_REDIS_TLS="true"

# ─── Configuration ───────────────────────────────────────────────────────────
LOG_FILE="redis_migration_$(date +%Y%m%d_%H%M%S).log"
BATCH_SIZE=100

# ─── Functions ───────────────────────────────────────────────────────────────
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

source_cli() {
  local tls_flag=""
  [ "$SOURCE_REDIS_TLS" == "true" ] && tls_flag="--tls"
  redis-cli -h "$SOURCE_REDIS_HOST" -p "$SOURCE_REDIS_PORT" \
    -a "$SOURCE_REDIS_PASSWORD" $tls_flag "$@"
}

target_cli() {
  local tls_flag=""
  [ "$TARGET_REDIS_TLS" == "true" ] && tls_flag="--tls"
  redis-cli -h "$TARGET_REDIS_HOST" -p "$TARGET_REDIS_PORT" \
    -a "$TARGET_REDIS_PASSWORD" $tls_flag "$@"
}

check_prerequisites() {
  log "Checking prerequisites..."
  command -v redis-cli >/dev/null 2>&1 || { log "ERROR: redis-cli not found"; exit 1; }
  log "Prerequisites OK"
}

test_connections() {
  log "Testing source connection (Render Key Value)..."
  source_cli PING >/dev/null 2>&1 || { log "ERROR: Cannot connect to source Redis"; exit 1; }
  log "Source connection OK"

  log "Testing target connection (AWS ElastiCache)..."
  target_cli PING >/dev/null 2>&1 || { log "ERROR: Cannot connect to target Redis"; exit 1; }
  log "Target connection OK"
}

get_source_info() {
  local dbsize
  dbsize=$(source_cli DBSIZE | awk '{print $NF}')
  log "Source database size: $dbsize keys"
  echo "$dbsize"
}

migrate_keys() {
  local total_keys migrated=0 failed=0
  total_keys=$(get_source_info)

  log "Starting key migration ($total_keys keys)..."

  source_cli --scan --pattern '*' | while IFS= read -r key; do
    # Get TTL
    local ttl
    ttl=$(source_cli TTL "$key")
    [ "$ttl" -lt 0 ] && ttl=0

    # Dump and restore
    local dump
    dump=$(source_cli DUMP "$key")

    if [ -n "$dump" ] && [ "$dump" != "" ]; then
      if target_cli RESTORE "$key" "$((ttl * 1000))" "$dump" REPLACE >/dev/null 2>&1; then
        migrated=$((migrated + 1))
      else
        failed=$((failed + 1))
        log "WARN: Failed to restore key: $key"
      fi
    fi

    # Progress report every BATCH_SIZE keys
    if [ $(( (migrated + failed) % BATCH_SIZE )) -eq 0 ]; then
      log "Progress: $((migrated + failed))/$total_keys (migrated=$migrated, failed=$failed)"
    fi
  done

  log "Migration complete: migrated=$migrated, failed=$failed"
}

verify_migration() {
  log "Verifying migration..."

  local source_count target_count
  source_count=$(source_cli DBSIZE | awk '{print $NF}')
  target_count=$(target_cli DBSIZE | awk '{print $NF}')

  log "Source key count: $source_count"
  log "Target key count: $target_count"

  if [ "$source_count" == "$target_count" ]; then
    log "Key counts match — migration verified"
  else
    log "WARNING: Key count mismatch (source=$source_count, target=$target_count)"
    log "  Possible causes: expired keys during migration, or failed restores above."
  fi
}

# ─── Main ────────────────────────────────────────────────────────────────────
main() {
  log "=== Redis Migration Started (Render Key Value -> AWS ElastiCache) ==="
  check_prerequisites
  test_connections
  migrate_keys
  verify_migration
  log "=== Redis Migration Complete ==="
  log "Log file: $LOG_FILE"
}

main "$@"
```

---

## Step 4: Set Script Permissions

After writing scripts, ensure they are executable:

```bash
chmod +x $MIGRATION_DIR/scripts/migrate-postgres.sh  # (if generated)
chmod +x $MIGRATION_DIR/scripts/migrate-redis.sh     # (if generated)
```

---

## Step 5: Validate Generated Documentation

Verify all generated files:

1. **MIGRATION_GUIDE.md** exists and:
   - Contains "Prerequisites" section
   - Contains "Phase 1: Infrastructure Provisioning" section
   - If `has_postgres`: Contains "PostgreSQL Migration" subsection
   - If `has_redis`: Contains "Redis Migration" subsection
   - If NOT `has_postgres`: Does NOT contain "PostgreSQL Migration" subsection
   - If NOT `has_redis`: Does NOT contain "Redis Migration" subsection
   - If `has_postgres`: Contains "Render Cutover Sequence" subsection
   - If `migration_method == "dms"`: Contains DMS limitation warning about CDC/continuous replication
   - If `migration_approach == "interim_cutover_data_first"`: Contains "Interim Database Access" section with TLS prerequisite gate and Render outbound IP allowlist steps
   - If `migration_approach == "interim_cutover_data_first"`: Contains "Interim Operation Advisory" section
   - Does NOT instruct opening a database port (5432) to `0.0.0.0/0` anywhere — interim access must be a scoped CIDR allowlist applied through Terraform
   - Contains "Post-Migration Lockdown" section
   - Contains "Config Var Migration" section for each compute type present
   - If has_beanstalk: Contains selected EB deploy method instructions, EB DNS cutover target, and no CodePipeline artifact unless `eb_deploy_method` is `"codepipeline"`
   - Contains "Verification" section with service-type-appropriate checks
   - If `deferred_services.length > 0`: Contains "Manual Migration Items" section

2. **README.md** exists and:
   - Lists all artifact files present in `$MIGRATION_DIR`
   - Includes terraform apply command sequence
   - References correct target region
   - Includes estimated monthly cost

3. **Scripts** (if generated):
   - `scripts/migrate-postgres.sh` exists if `has_postgres`
   - `scripts/migrate-redis.sh` exists if `has_redis`
   - Scripts contain connection parameter placeholders (not real credentials)
   - Scripts are executable (`chmod +x` applied)

---

## Error Handling

| Error                          | Behavior                                        | Impact                                 |
| ------------------------------ | ----------------------------------------------- | -------------------------------------- |
| Template variable unresolvable | Use placeholder with `{{VARIABLE_NAME}}` format | User fills manually                    |
| No data stores in design       | Omit Phase 2 entirely from guide                | Valid — compute-only migration         |
| No deferred services           | Omit Manual Migration Items section             | Valid — all services mapped            |
| Both data stores absent        | MIGRATION_GUIDE still generated (compute-only)  | Valid migration path                   |
| Script write failure           | Log warning, continue with remaining files      | Parent captures in generation-warnings |
