"""Generate migration documentation and scripts.

Reads aws-design.json + preferences.json + inventory, produces:
- MIGRATION_GUIDE.md (step-by-step migration procedure)
- README.md (artifact listing)
- scripts/migrate-postgres.sh (if postgres in design)
- scripts/migrate-redis.sh (if redis in design)
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("engine.generate_docs")


def _read_json(path: Path) -> dict | None:
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def _detect_services(design: dict) -> dict:
    """Detect which service types are in the design."""
    services = design.get("services", [])
    aws_types = {s.get("aws_service", "") for s in services}
    return {
        "has_postgres": "RDS PostgreSQL" in aws_types or "Aurora PostgreSQL" in aws_types,
        "has_redis": "ElastiCache Redis" in aws_types,
        "has_kafka": "Amazon MSK" in aws_types,
        "has_fargate": "Fargate" in aws_types,
        "has_alb": "ALB" in aws_types,
    }


def _build_migration_guide(design: dict, preferences: dict, inventory: dict, svc_flags: dict) -> str:
    """Build MIGRATION_GUIDE.md content."""
    region = preferences.get("global", {}).get("target_region", "us-east-1")
    apps = [a.get("app_name", "app") for a in inventory.get("apps", [])]
    apps_str = ", ".join(apps) if apps else "your-app"
    approach = preferences.get("global", {}).get("migration_approach", "full_cutover")
    exit_date = preferences.get("global", {}).get("target_exit_date", "not set")

    lines = [
        "# Heroku-to-AWS Migration Guide",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        f"Target region: `{region}`",
        f"Apps: {apps_str}",
        f"Approach: {approach}",
        f"Target exit date: {exit_date}",
        "",
        "## Table of Contents",
        "",
        "1. [Prerequisites](#prerequisites)",
        "2. [Phase 1: Infrastructure Provisioning](#phase-1-infrastructure-provisioning)",
    ]

    if svc_flags["has_postgres"] or svc_flags["has_redis"] or svc_flags["has_kafka"]:
        lines.append("3. [Phase 2: Data Migration](#phase-2-data-migration)")
    lines.extend([
        f"{'4' if svc_flags['has_postgres'] or svc_flags['has_redis'] or svc_flags['has_kafka'] else '3'}. [Phase 3: Application Deployment](#phase-3-application-deployment)",
        f"{'5' if svc_flags['has_postgres'] or svc_flags['has_redis'] or svc_flags['has_kafka'] else '4'}. [Phase 4: Verification](#phase-4-verification)",
        f"{'6' if svc_flags['has_postgres'] or svc_flags['has_redis'] or svc_flags['has_kafka'] else '5'}. [Phase 5: Cutover](#phase-5-cutover)",
        "",
        "## Prerequisites",
        "",
        "### AWS Account Setup",
        "- [ ] AWS account with appropriate permissions",
        "- [ ] AWS CLI configured with credentials",
        "- [ ] Terraform >= 1.5.0 installed",
        f"- [ ] Target region: `{region}`",
        "",
        "### Heroku Access",
        "- [ ] Heroku CLI installed and authenticated",
        "- [ ] Access to all apps being migrated",
    ])

    if svc_flags["has_postgres"]:
        lines.append("- [ ] `heroku pg:credentials:url` access for database connection strings")
    if svc_flags["has_redis"]:
        lines.append("- [ ] `heroku redis:credentials` access")

    lines.extend([
        "",
        "### ⚠️ Platform Risk Advisory",
        "",
        "> Heroku is in sustaining engineering (KTLO) mode. No new features, no enterprise contracts",
        "> for new customers. Plan for complete platform exit within your target window.",
        "",
        "## Phase 1: Infrastructure Provisioning",
        "",
        "```bash",
        "cd terraform/",
        "terraform init",
        "terraform plan -out=tfplan",
        "terraform apply tfplan",
        "```",
        "",
        "Save Terraform outputs for subsequent phases:",
        "```bash",
        "terraform output -json > ../terraform-outputs.json",
        "```",
        "",
    ])

    # Phase 2: Data Migration
    if svc_flags["has_postgres"] or svc_flags["has_redis"] or svc_flags["has_kafka"]:
        lines.extend(["## Phase 2: Data Migration", ""])

        if svc_flags["has_postgres"]:
            lines.extend([
                "### PostgreSQL Migration",
                "",
                "**Method: pg_dump/pg_restore (one-time bulk migration)**",
                "",
                "> ⚠️ Heroku Postgres does not grant REPLICATION role. AWS DMS cannot perform",
                "> continuous replication (CDC). Use pg_dump for one-time migration with a cutover window.",
                "",
                "```bash",
                "# Run the migration script",
                "chmod +x scripts/migrate-postgres.sh",
                "./scripts/migrate-postgres.sh",
                "```",
                "",
                "See `scripts/migrate-postgres.sh` for the full procedure.",
                "",
            ])

        if svc_flags["has_redis"]:
            lines.extend([
                "### Redis Migration",
                "",
                "```bash",
                "chmod +x scripts/migrate-redis.sh",
                "./scripts/migrate-redis.sh",
                "```",
                "",
                "See `scripts/migrate-redis.sh` for the full procedure.",
                "",
            ])

        if svc_flags["has_kafka"]:
            lines.extend([
                "### Kafka Migration",
                "",
                "Kafka topic migration requires MirrorMaker2 or manual topic recreation.",
                "See AWS MSK documentation for details.",
                "",
            ])

    # Phase 3: Application Deployment
    lines.extend([
        "## Phase 3: Application Deployment",
        "",
        "### Build and Push Container Image",
        "",
        "```bash",
        "# Build container image",
        "docker build -t {{AWS_ACCOUNT_ID}}.dkr.ecr.{}.amazonaws.com/{{app_name}}:latest .".format(region),
        "",
        "# Authenticate to ECR",
        f"aws ecr get-login-password --region {region} | docker login --username AWS --password-stdin {{{{AWS_ACCOUNT_ID}}}}.dkr.ecr.{region}.amazonaws.com",
        "",
        "# Push image",
        "docker push {{AWS_ACCOUNT_ID}}.dkr.ecr.{}.amazonaws.com/{{app_name}}:latest".format(region),
        "```",
        "",
        "### Deploy to Fargate",
        "",
        "```bash",
        "# Update ECS service with new task definition",
        "aws ecs update-service --cluster $(terraform output -raw ecs_cluster_name) --service {{app_name}}-web --force-new-deployment",
        "```",
        "",
        "## Phase 4: Verification",
        "",
        "- [ ] ALB health check passing",
        "- [ ] Application responding on ALB DNS",
    ])
    if svc_flags["has_postgres"]:
        lines.append("- [ ] Database connectivity verified")
    if svc_flags["has_redis"]:
        lines.append("- [ ] Redis connectivity verified")
    lines.extend([
        "- [ ] Logs flowing to CloudWatch",
        "- [ ] No errors in ECS task events",
        "",
        "## Phase 5: Cutover",
        "",
        "### DNS Cutover",
        "1. Update DNS records to point to ALB DNS name",
        "2. Set TTL low (60s) before cutover for fast rollback",
        "3. Monitor error rates for 15 minutes post-cutover",
        "",
        "### Decommission Heroku",
        "After validation period (recommended: 48-72 hours):",
        "1. Scale Heroku dynos to 0",
        "2. Remove Heroku add-ons",
        "3. Delete Heroku apps",
        "",
    ])

    # Deferred items
    deferred = design.get("deferred", [])
    if deferred:
        lines.extend(["## Manual Migration Items", ""])
        for d in deferred:
            lines.append(f"- **{d.get('addon_name', 'unknown')}** ({d.get('addon_plan', '')}): {d.get('recommendation', 'Engage AWS account team')}")
        lines.append("")

    return "\n".join(lines)


def _build_readme(design: dict, migration_dir: Path, svc_flags: dict) -> str:
    """Build README.md content."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    services = design.get("services", [])

    lines = [
        "# Heroku-to-AWS Migration Artifacts",
        "",
        f"Generated: {timestamp}",
        "",
        "## Artifact Files",
        "",
        "| File | Description |",
        "|------|-------------|",
        "| `terraform/main.tf` | AWS provider configuration |",
        "| `terraform/variables.tf` | Input variables |",
        "| `terraform/vpc.tf` | VPC and networking |",
        "| `terraform/security.tf` | Security groups and IAM |",
    ]

    if svc_flags["has_fargate"]:
        lines.append("| `terraform/compute.tf` | ECS cluster, task definitions, services, ALBs |")
    if svc_flags["has_postgres"]:
        lines.append("| `terraform/database.tf` | RDS/Aurora PostgreSQL |")
    if svc_flags["has_redis"]:
        lines.append("| `terraform/cache.tf` | ElastiCache Redis |")
    if svc_flags["has_kafka"]:
        lines.append("| `terraform/messaging.tf` | Amazon MSK |")

    lines.extend([
        "| `terraform/outputs.tf` | Resource outputs |",
        "| `MIGRATION_GUIDE.md` | Step-by-step migration procedure |",
    ])

    if svc_flags["has_postgres"]:
        lines.append("| `scripts/migrate-postgres.sh` | PostgreSQL data migration script |")
    if svc_flags["has_redis"]:
        lines.append("| `scripts/migrate-redis.sh` | Redis data migration script |")

    lines.extend([
        "",
        "## Quick Start",
        "",
        "```bash",
        "# 1. Review and customize variables",
        "cd terraform/",
        "cp terraform.tfvars.example terraform.tfvars",
        "# Edit terraform.tfvars with your values",
        "",
        "# 2. Apply infrastructure",
        "terraform init",
        "terraform plan",
        "terraform apply",
        "",
        "# 3. Follow MIGRATION_GUIDE.md for data migration and cutover",
        "```",
        "",
        "## Important Notes",
        "",
        "- Review all `{{PLACEHOLDER}}` values before executing",
        "- Test in a staging environment before production cutover",
        "- Heroku does not support CDC replication — plan for a maintenance window",
        f"- Total designed services: {len(services)}",
        "",
    ])

    return "\n".join(lines)


def _build_postgres_script(design: dict, preferences: dict) -> str:
    """Build migrate-postgres.sh script."""
    region = preferences.get("global", {}).get("target_region", "us-east-1")
    return f"""#!/bin/bash
set -euo pipefail

# PostgreSQL Migration: Heroku Postgres → RDS/Aurora
# Generated by heroku-to-aws migration engine
#
# ⚠️ Heroku does not grant REPLICATION role — CDC is not possible.
# This script performs a one-time bulk migration via pg_dump/pg_restore.

echo "=== PostgreSQL Migration ==="
echo "Region: {region}"
echo ""

# --- FILL THESE VALUES ---
SOURCE_DB_URL="{{{{SOURCE_DB_URL}}}}"  # From: heroku pg:credentials:url -a <app>
TARGET_DB_HOST="{{{{TARGET_DB_HOST}}}}"  # From: terraform output rds_endpoint
TARGET_DB_NAME="{{{{TARGET_DB_NAME}}}}"
TARGET_DB_USER="{{{{TARGET_DB_USER}}}}"
TARGET_DB_PASS="{{{{TARGET_DB_PASS}}}}"
# -------------------------

echo "Step 1: Put application in maintenance mode"
echo "  heroku maintenance:on -a <app>"
read -p "Press Enter when maintenance mode is active..."

echo "Step 2: Dump source database"
pg_dump "$SOURCE_DB_URL" --format=custom --no-owner --no-acl -f /tmp/heroku-pg-dump.dump
echo "  Dump complete: $(du -sh /tmp/heroku-pg-dump.dump | cut -f1)"

echo "Step 3: Restore to target"
PGPASSWORD="$TARGET_DB_PASS" pg_restore \\
  --host="$TARGET_DB_HOST" \\
  --dbname="$TARGET_DB_NAME" \\
  --username="$TARGET_DB_USER" \\
  --no-owner --no-acl \\
  /tmp/heroku-pg-dump.dump

echo "Step 4: Verify row counts"
echo "  Run verification queries against both source and target."

echo ""
echo "✅ PostgreSQL migration complete."
echo "   Next: Update application DATABASE_URL to point to RDS/Aurora."
"""


def _build_redis_script(design: dict, preferences: dict) -> str:
    """Build migrate-redis.sh script."""
    return """#!/bin/bash
set -euo pipefail

# Redis Migration: Heroku Redis → ElastiCache
# Generated by heroku-to-aws migration engine

echo "=== Redis Migration ==="

# --- FILL THESE VALUES ---
SOURCE_REDIS_URL="{{SOURCE_REDIS_URL}}"  # From: heroku redis:credentials -a <app>
TARGET_REDIS_HOST="{{TARGET_REDIS_HOST}}"  # From: terraform output elasticache_endpoint
TARGET_REDIS_PORT=6379
# -------------------------

echo "Step 1: Export keys from source (if persistent data needed)"
echo "  Note: If Redis is used only for caching, skip migration — let cache warm naturally."
read -p "Migrate Redis data? (y/N): " MIGRATE

if [[ "$MIGRATE" == "y" || "$MIGRATE" == "Y" ]]; then
  echo "Step 2: Dump and restore using redis-cli"
  redis-cli -u "$SOURCE_REDIS_URL" --rdb /tmp/heroku-redis-dump.rdb
  redis-cli -h "$TARGET_REDIS_HOST" -p $TARGET_REDIS_PORT --pipe < /tmp/heroku-redis-dump.rdb
  echo "  Redis data migrated."
else
  echo "  Skipping Redis data migration (cache-only mode)."
fi

echo ""
echo "✅ Redis migration complete."
echo "   Next: Update application REDIS_URL to point to ElastiCache."
"""


def generate_docs(migration_dir: str, knowledge: dict) -> dict[str, Any]:
    """Generate migration documentation and scripts.

    Args:
        migration_dir: Path to migration run directory.
        knowledge: Knowledge store dict (unused for docs but kept for signature consistency).

    Returns:
        Dict with status and list of files written.
    """
    mdir = Path(migration_dir)
    design = _read_json(mdir / "aws-design.json")
    preferences = _read_json(mdir / "preferences.json")
    inventory = _read_json(mdir / "heroku-resource-inventory.json")

    if not design:
        return {"status": "error", "reason": "aws-design.json not found"}
    if not preferences:
        return {"status": "error", "reason": "preferences.json not found"}

    svc_flags = _detect_services(design)
    files_written = []

    # MIGRATION_GUIDE.md
    guide = _build_migration_guide(design, preferences, inventory or {}, svc_flags)
    (mdir / "MIGRATION_GUIDE.md").write_text(guide)
    files_written.append("MIGRATION_GUIDE.md")

    # README.md
    readme = _build_readme(design, mdir, svc_flags)
    (mdir / "README.md").write_text(readme)
    files_written.append("README.md")

    # Scripts
    scripts_dir = mdir / "scripts"
    if svc_flags["has_postgres"] or svc_flags["has_redis"]:
        scripts_dir.mkdir(exist_ok=True)

    if svc_flags["has_postgres"]:
        pg_script = _build_postgres_script(design, preferences)
        pg_path = scripts_dir / "migrate-postgres.sh"
        pg_path.write_text(pg_script)
        os.chmod(pg_path, 0o755)
        files_written.append("scripts/migrate-postgres.sh")

    if svc_flags["has_redis"]:
        redis_script = _build_redis_script(design, preferences)
        redis_path = scripts_dir / "migrate-redis.sh"
        redis_path.write_text(redis_script)
        os.chmod(redis_path, 0o755)
        files_written.append("scripts/migrate-redis.sh")

    logger.info("Generated %d doc/script files in %s", len(files_written), mdir)

    return {"status": "ok", "files_written": files_written}
