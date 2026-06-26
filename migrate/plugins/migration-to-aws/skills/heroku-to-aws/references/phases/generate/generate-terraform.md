# Generate Phase: Terraform Configurations

> Generates all Terraform .tf files from `aws-design.json` using templates.
> Produces the `terraform/` directory in `$MIGRATION_DIR`.

---

## Step 1: Generate Terraform

Call the `heroku_generate_terraform` MCP tool:

```
heroku_generate_terraform(migration_dir=$MIGRATION_DIR)
```

This tool reads `aws-design.json` and `preferences.json`, then:

- Renders `main.tf` (provider config with default tags)
- Renders `variables.tf` (region, project name, VPC CIDR)
- Renders `vpc.tf` (new VPC with subnets or existing VPC reference)
- Renders `security.tf` (security groups for ALB, app, database, cache, messaging + IAM roles)
- Renders `compute.tf` (ECS cluster, task definitions, services, ALBs — one per Fargate service)
- Renders `database.tf` (RDS/Aurora instances, subnet groups, RDS Proxy if needed)
- Renders `cache.tf` (ElastiCache replication groups)
- Renders `messaging.tf` (MSK clusters)
- Renders `outputs.tf` + `.gitignore`

All files use HCL templates from `knowledge/heroku-to-aws/templates/`.

---

## Step 2: Review Output

Check the tool's return:

- `files_written` — list of generated .tf files
- If any expected file is missing (e.g., `database.tf` when postgres is in design), investigate

Verify no placeholder values remain: search `terraform/*.tf` for `__` (double underscore). If found, the template substitution missed a value — fix manually.

---

## Scope Boundary

FORBIDDEN — Do NOT:

- Modify the design (Phase 3 is final)
- Add resources not in `aws-design.json`
- Generate cost estimates (Phase 4 did that)
