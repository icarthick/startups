"""Tests for estimate_heroku_migration tool (incl. EKS cost path)."""

import json
from pathlib import Path

import pytest

from engine.knowledge import load_knowledge
from engine.tools.heroku.design import design_heroku_migration
from engine.tools.heroku.estimate import estimate_heroku_migration

KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "knowledge"


@pytest.fixture
def knowledge():
    return load_knowledge(KNOWLEDGE_DIR)


def _setup(tmp_path, kube_value=None):
    inventory = {
        "resources": [
            {"resource_id": "formation:api:web", "resource_type": "formation", "heroku_app": "api", "config": {"process_type": "web", "dyno_type": "performance-l", "quantity": 2}},
            {"resource_id": "formation:api:worker", "resource_type": "formation", "heroku_app": "api", "config": {"process_type": "worker", "dyno_type": "standard-2x", "quantity": 1}},
            {"resource_id": "addon:api:heroku-postgresql:standard-0", "resource_type": "addon", "heroku_app": "api", "config": {"addon_service": "heroku-postgresql", "plan": "standard-0"}},
        ],
        "apps": [{"app_name": "api", "heroku_generation": "cedar"}],
        "metadata": {"discovery_sources": ["terraform"]},
    }
    prefs = {"global": {"target_region": "us-east-1", "availability": "multi-az"}, "operational": {"log_retention_days": 30}}
    if kube_value:
        prefs["design_constraints"] = {"kubernetes": {"value": kube_value}}
    (tmp_path / "heroku-resource-inventory.json").write_text(json.dumps(inventory))
    (tmp_path / "preferences.json").write_text(json.dumps(prefs))
    return tmp_path


class TestFargateEstimate:
    def test_produces_estimate(self, tmp_path, knowledge):
        _setup(tmp_path)
        design_heroku_migration(str(tmp_path), knowledge)
        result = estimate_heroku_migration(str(tmp_path), knowledge)
        assert result["status"] == "ok"
        assert (tmp_path / "estimation-infra.json").exists()

    def test_no_eks_lines_in_fargate(self, tmp_path, knowledge):
        _setup(tmp_path, "ecs-fargate")
        design_heroku_migration(str(tmp_path), knowledge)
        estimate_heroku_migration(str(tmp_path), knowledge)
        est = json.loads((tmp_path / "estimation-infra.json").read_text())
        ids = [b["service_id"] for b in est["projected_costs"]["breakdown"]]
        assert "eks_control_plane" not in ids
        assert est["notes"] == []

    def test_unavailable_when_no_billing(self, tmp_path, knowledge):
        _setup(tmp_path)
        design_heroku_migration(str(tmp_path), knowledge)
        estimate_heroku_migration(str(tmp_path), knowledge)
        est = json.loads((tmp_path / "estimation-infra.json").read_text())
        assert est["current_costs"]["source"] == "unavailable"


class TestEksEstimate:
    def test_eks_cluster_cost_lines(self, tmp_path, knowledge):
        _setup(tmp_path, "eks-managed")
        design_heroku_migration(str(tmp_path), knowledge)
        estimate_heroku_migration(str(tmp_path), knowledge)
        est = json.loads((tmp_path / "estimation-infra.json").read_text())
        bd = {b["service_id"]: b["monthly_cost"] for b in est["projected_costs"]["breakdown"]}
        assert bd["eks_control_plane"] == 73.00
        # largest dyno performance-l -> m6i.4xlarge @ 0.768/hr, desired=ceil(3/4)=1 node
        assert bd["eks_nodes"] == round(0.768 * 730 * 1, 2)

    def test_no_eks_pod_lines_in_breakdown(self, tmp_path, knowledge):
        _setup(tmp_path, "eks-managed")
        design_heroku_migration(str(tmp_path), knowledge)
        estimate_heroku_migration(str(tmp_path), knowledge)
        est = json.loads((tmp_path / "estimation-infra.json").read_text())
        ids = [b["service_id"] for b in est["projected_costs"]["breakdown"]]
        assert not any(i.startswith("eks:") for i in ids)  # pod lines omitted

    def test_eks_note_present(self, tmp_path, knowledge):
        _setup(tmp_path, "eks-managed")
        design_heroku_migration(str(tmp_path), knowledge)
        estimate_heroku_migration(str(tmp_path), knowledge)
        est = json.loads((tmp_path / "estimation-infra.json").read_text())
        assert len(est["notes"]) == 1
        assert "EKS" in est["notes"][0]

    def test_eks_cost_in_balanced_total(self, tmp_path, knowledge):
        _setup(tmp_path, "eks-managed")
        design_heroku_migration(str(tmp_path), knowledge)
        estimate_heroku_migration(str(tmp_path), knowledge)
        est = json.loads((tmp_path / "estimation-infra.json").read_text())
        # balanced must include control plane + nodes
        assert est["projected_costs"]["aws_monthly_balanced"] > 73.0 + 560.0
