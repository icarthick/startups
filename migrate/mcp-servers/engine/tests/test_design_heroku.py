"""Tests for design_heroku_migration tool."""

import json
from pathlib import Path

import pytest

from engine.knowledge import load_knowledge
from engine.tools.heroku.design import design_heroku_migration

KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "knowledge"


@pytest.fixture
def knowledge():
    return load_knowledge(KNOWLEDGE_DIR)


@pytest.fixture
def migration_dir(tmp_path):
    """Set up a migration dir with inventory + preferences."""
    inventory = {
        "resources": [
            {"resource_id": "app:my-app", "resource_type": "app", "heroku_app": "my-app", "config": {"app_name": "my-app", "stack": "heroku-22"}},
            {"resource_id": "formation:my-app:web", "resource_type": "formation", "heroku_app": "my-app", "config": {"process_type": "web", "dyno_type": "standard-2x", "quantity": 2, "command": "gunicorn app:app"}},
            {"resource_id": "formation:my-app:worker", "resource_type": "formation", "heroku_app": "my-app", "config": {"process_type": "worker", "dyno_type": "standard-1x", "quantity": 1, "command": "celery worker"}},
            {"resource_id": "addon:my-app:heroku-postgresql:standard-0", "resource_type": "addon", "heroku_app": "my-app", "config": {"addon_service": "heroku-postgresql", "plan": "standard-0", "provider": "heroku"}},
            {"resource_id": "addon:my-app:heroku-redis:premium-3", "resource_type": "addon", "heroku_app": "my-app", "config": {"addon_service": "heroku-redis", "plan": "premium-3", "provider": "heroku"}},
            {"resource_id": "addon:my-app:papertrail:choklad", "resource_type": "addon", "heroku_app": "my-app", "config": {"addon_service": "papertrail", "plan": "choklad", "provider": "papertrail"}},
        ],
        "apps": [{"app_name": "my-app", "heroku_generation": "cedar", "generation_action": "detect_only", "space": None}],
        "metadata": {"discovery_sources": ["terraform"], "total_apps_discovered": 1},
    }
    preferences = {
        "global": {"target_region": "us-west-2", "availability": "multi-az"},
        "data": {"database_ha": "multi-az"},
        "operational": {"log_retention_days": 14},
    }
    (tmp_path / "heroku-resource-inventory.json").write_text(json.dumps(inventory))
    (tmp_path / "preferences.json").write_text(json.dumps(preferences))
    return tmp_path


class TestDesignBasic:
    def test_produces_design(self, migration_dir, knowledge):
        result = design_heroku_migration(str(migration_dir), knowledge)
        assert result["status"] == "ok"
        assert (migration_dir / "aws-design.json").exists()

    def test_service_count(self, migration_dir, knowledge):
        result = design_heroku_migration(str(migration_dir), knowledge)
        # web fargate + ALB + worker fargate + RDS + ElastiCache + CloudWatch Logs = 6
        assert result["summary"]["total_services"] == 6

    def test_missing_inventory(self, tmp_path, knowledge):
        (tmp_path / "preferences.json").write_text("{}")
        result = design_heroku_migration(str(tmp_path), knowledge)
        assert result["status"] == "error"


class TestFormationMapping:
    def test_fargate_sizing(self, migration_dir, knowledge):
        design_heroku_migration(str(migration_dir), knowledge)
        design = json.loads((migration_dir / "aws-design.json").read_text())
        web = next(s for s in design["services"] if s["service_id"] == "fargate:my-app:web")
        assert web["aws_config"]["task_cpu"] == 512
        assert web["aws_config"]["task_memory"] == 1024
        assert web["aws_config"]["desired_count"] == 2

    def test_alb_for_web(self, migration_dir, knowledge):
        design_heroku_migration(str(migration_dir), knowledge)
        design = json.loads((migration_dir / "aws-design.json").read_text())
        alb = next(s for s in design["services"] if s["aws_service"] == "ALB")
        assert alb["aws_config"]["scheme"] == "internet-facing"

    def test_no_alb_for_worker(self, migration_dir, knowledge):
        design_heroku_migration(str(migration_dir), knowledge)
        design = json.loads((migration_dir / "aws-design.json").read_text())
        albs = [s for s in design["services"] if s["aws_service"] == "ALB"]
        assert len(albs) == 1  # Only web gets ALB

    def test_unknown_dyno_warning(self, tmp_path, knowledge):
        inventory = {"resources": [{"resource_id": "formation:x:web", "resource_type": "formation", "heroku_app": "x", "config": {"process_type": "web", "dyno_type": "mega-xl", "quantity": 1}}], "apps": [], "metadata": {"discovery_sources": ["terraform"]}}
        (tmp_path / "heroku-resource-inventory.json").write_text(json.dumps(inventory))
        (tmp_path / "preferences.json").write_text(json.dumps({"global": {}}))
        result = design_heroku_migration(str(tmp_path), knowledge)
        design = json.loads((tmp_path / "aws-design.json").read_text())
        assert any("mega-xl" in w for w in design["warnings"])


class TestPostgresMapping:
    def test_rds_for_multi_az(self, migration_dir, knowledge):
        design_heroku_migration(str(migration_dir), knowledge)
        design = json.loads((migration_dir / "aws-design.json").read_text())
        rds = next(s for s in design["services"] if "rds" in s["service_id"])
        assert rds["aws_service"] == "RDS PostgreSQL"
        assert rds["aws_config"]["instance_class"] == "db.t4g.medium"
        assert rds["aws_config"]["rds_proxy"] is True

    def test_aurora_for_multi_az_ha(self, tmp_path, knowledge):
        inventory = {"resources": [{"resource_id": "addon:x:heroku-postgresql:standard-2", "resource_type": "addon", "heroku_app": "x", "config": {"addon_service": "heroku-postgresql", "plan": "standard-2"}}], "apps": [], "metadata": {"discovery_sources": ["terraform"]}}
        prefs = {"global": {}, "data": {"database_ha": "multi-az-ha"}}
        (tmp_path / "heroku-resource-inventory.json").write_text(json.dumps(inventory))
        (tmp_path / "preferences.json").write_text(json.dumps(prefs))
        design_heroku_migration(str(tmp_path), knowledge)
        design = json.loads((tmp_path / "aws-design.json").read_text())
        rds = next(s for s in design["services"] if "rds" in s["service_id"])
        assert rds["aws_service"] == "Aurora PostgreSQL"
        assert rds["aws_config"]["instance_class"] == "db.r6g.large"


class TestFastPath:
    def test_papertrail_maps(self, migration_dir, knowledge):
        design_heroku_migration(str(migration_dir), knowledge)
        design = json.loads((migration_dir / "aws-design.json").read_text())
        cw = next(s for s in design["services"] if "papertrail" in s["service_id"])
        assert "CloudWatch Logs" in cw["aws_service"]

    def test_unknown_addon_deferred(self, tmp_path, knowledge):
        inventory = {"resources": [{"resource_id": "addon:x:obscure-addon:pro", "resource_type": "addon", "heroku_app": "x", "config": {"addon_service": "obscure-addon", "plan": "pro", "provider": "third-party"}}], "apps": [], "metadata": {"discovery_sources": ["terraform"]}}
        (tmp_path / "heroku-resource-inventory.json").write_text(json.dumps(inventory))
        (tmp_path / "preferences.json").write_text(json.dumps({"global": {}}))
        design_heroku_migration(str(tmp_path), knowledge)
        design = json.loads((tmp_path / "aws-design.json").read_text())
        assert len(design["deferred"]) == 1
        assert design["deferred"][0]["addon_name"] == "obscure-addon"


class TestVpcDesign:
    def test_new_vpc_default(self, migration_dir, knowledge):
        design_heroku_migration(str(migration_dir), knowledge)
        design = json.loads((migration_dir / "aws-design.json").read_text())
        assert design["vpc_design"]["mode"] == "new_vpc"
        assert len(design["vpc_design"]["subnets"]) == 4
