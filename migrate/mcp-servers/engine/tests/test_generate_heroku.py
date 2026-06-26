"""Tests for generate_terraform + generate_docs tools (incl. EKS path).

Also guards the templates-directory resolution (a prior file move broke it,
silently producing no output because there were no generate tests).
"""

import json
import re
from pathlib import Path

import pytest

from engine.knowledge import load_knowledge
from engine.tools.heroku.design import design_heroku_migration
from engine.tools.heroku.generate.terraform import generate_terraform
from engine.tools.heroku.generate.docs import generate_docs

KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "knowledge"


@pytest.fixture
def knowledge():
    return load_knowledge(KNOWLEDGE_DIR)


def _setup(tmp_path, kube_value=None, with_redis=False):
    resources = [
        {"resource_id": "formation:api:web", "resource_type": "formation", "heroku_app": "api", "config": {"process_type": "web", "dyno_type": "performance-l", "quantity": 2}},
        {"resource_id": "formation:api:worker", "resource_type": "formation", "heroku_app": "api", "config": {"process_type": "worker", "dyno_type": "standard-2x", "quantity": 1}},
        {"resource_id": "addon:api:heroku-postgresql:standard-0", "resource_type": "addon", "heroku_app": "api", "config": {"addon_service": "heroku-postgresql", "plan": "standard-0"}},
    ]
    if with_redis:
        resources.append({"resource_id": "addon:api:heroku-redis:premium-0", "resource_type": "addon", "heroku_app": "api", "config": {"addon_service": "heroku-redis", "plan": "premium-0"}})
    inventory = {"resources": resources, "apps": [{"app_name": "api", "heroku_generation": "cedar"}], "metadata": {"discovery_sources": ["terraform"]}}
    prefs = {"global": {"target_region": "us-east-1", "availability": "multi-az"}, "operational": {"log_retention_days": 30}}
    if kube_value:
        prefs["design_constraints"] = {"kubernetes": {"value": kube_value}}
    (tmp_path / "heroku-resource-inventory.json").write_text(json.dumps(inventory))
    (tmp_path / "preferences.json").write_text(json.dumps(prefs))
    return tmp_path


def _no_unsubstituted(text):
    """Allow only intentional user-fill placeholders."""
    leftovers = [p for p in re.findall(r"{{(\w+)}}", text) if p not in ("AWS_ACCOUNT_ID", "app_name", "SOURCE_DB_URL", "TARGET_DB_HOST", "TARGET_DB_NAME", "TARGET_DB_USER", "TARGET_DB_PASS", "SOURCE_REDIS_URL", "TARGET_REDIS_HOST")]
    return leftovers


class TestFargateGenerate:
    def test_templates_dir_resolves(self, tmp_path, knowledge):
        """Regression: generator must find its templates dir (prior bug returned error)."""
        _setup(tmp_path, "ecs-fargate")
        design_heroku_migration(str(tmp_path), knowledge)
        result = generate_terraform(str(tmp_path), knowledge)
        assert result["status"] == "ok"
        assert "main.tf" in result["files_written"]
        assert "compute.tf" in result["files_written"]

    def test_no_eks_tf_in_fargate(self, tmp_path, knowledge):
        _setup(tmp_path, "ecs-fargate")
        design_heroku_migration(str(tmp_path), knowledge)
        result = generate_terraform(str(tmp_path), knowledge)
        assert "eks.tf" not in result["files_written"]

    def test_no_placeholders_left(self, tmp_path, knowledge):
        _setup(tmp_path, "ecs-fargate")
        design_heroku_migration(str(tmp_path), knowledge)
        result = generate_terraform(str(tmp_path), knowledge)
        all_tf = "".join((tmp_path / "terraform" / f).read_text() for f in result["files_written"] if f.endswith(".tf"))
        assert _no_unsubstituted(all_tf) == []


class TestEksGenerate:
    def test_eks_tf_written(self, tmp_path, knowledge):
        _setup(tmp_path, "eks-managed")
        design_heroku_migration(str(tmp_path), knowledge)
        result = generate_terraform(str(tmp_path), knowledge)
        assert "eks.tf" in result["files_written"]

    def test_self_managed_node_group_only(self, tmp_path, knowledge):
        _setup(tmp_path, "eks-managed")
        design_heroku_migration(str(tmp_path), knowledge)
        generate_terraform(str(tmp_path), knowledge)
        eks = (tmp_path / "terraform" / "eks.tf").read_text()
        assert "aws_autoscaling_group" in eks  # self-managed
        assert "aws_eks_node_group" not in eks  # not managed

    def test_managed_node_group_only(self, tmp_path, knowledge):
        _setup(tmp_path, "eks-or-ecs")
        design_heroku_migration(str(tmp_path), knowledge)
        generate_terraform(str(tmp_path), knowledge)
        eks = (tmp_path / "terraform" / "eks.tf").read_text()
        assert "aws_eks_node_group" in eks  # managed
        assert "aws_autoscaling_group" not in eks  # not self-managed

    def test_eks_no_placeholders(self, tmp_path, knowledge):
        _setup(tmp_path, "eks-managed")
        design_heroku_migration(str(tmp_path), knowledge)
        generate_terraform(str(tmp_path), knowledge)
        eks = (tmp_path / "terraform" / "eks.tf").read_text()
        assert re.findall(r"{{[^}]+}}", eks) == []

    def test_datastore_sg_rules_self_managed(self, tmp_path, knowledge):
        _setup(tmp_path, "eks-managed", with_redis=True)
        design_heroku_migration(str(tmp_path), knowledge)
        generate_terraform(str(tmp_path), knowledge)
        eks = (tmp_path / "terraform" / "eks.tf").read_text()
        assert "pods_to_database" in eks
        assert "pods_to_cache" in eks

    def test_helm_tls_providers(self, tmp_path, knowledge):
        _setup(tmp_path, "eks-managed")
        design_heroku_migration(str(tmp_path), knowledge)
        generate_terraform(str(tmp_path), knowledge)
        eks = (tmp_path / "terraform" / "eks.tf").read_text()
        assert "hashicorp/helm" in eks and "hashicorp/tls" in eks


class TestEksDocs:
    def test_k8s_manifests_written(self, tmp_path, knowledge):
        _setup(tmp_path, "eks-managed")
        design_heroku_migration(str(tmp_path), knowledge)
        result = generate_docs(str(tmp_path), knowledge)
        assert any("kubernetes/" in f for f in result["files_written"])
        assert (tmp_path / "kubernetes" / "api-namespace.yaml").exists()

    def test_web_service_only_for_web(self, tmp_path, knowledge):
        _setup(tmp_path, "eks-managed")
        design_heroku_migration(str(tmp_path), knowledge)
        generate_docs(str(tmp_path), knowledge)
        assert (tmp_path / "kubernetes" / "api-web-service.yaml").exists()
        assert not (tmp_path / "kubernetes" / "api-worker-service.yaml").exists()

    def test_guide_has_eks_not_fargate(self, tmp_path, knowledge):
        _setup(tmp_path, "eks-managed")
        design_heroku_migration(str(tmp_path), knowledge)
        generate_docs(str(tmp_path), knowledge)
        guide = (tmp_path / "MIGRATION_GUIDE.md").read_text()
        assert "EKS Cluster Setup" in guide
        assert "Deploy to Fargate" not in guide

    def test_fargate_docs_no_k8s(self, tmp_path, knowledge):
        _setup(tmp_path, "ecs-fargate")
        design_heroku_migration(str(tmp_path), knowledge)
        result = generate_docs(str(tmp_path), knowledge)
        assert not any("kubernetes" in f for f in result["files_written"])
        guide = (tmp_path / "MIGRATION_GUIDE.md").read_text()
        assert "Deploy to Fargate" in guide
