"""Tests for generate_migration_preview tool."""

import json
from pathlib import Path

import pytest

from migration_orchestrator.knowledge import load_knowledge
from migration_orchestrator.tools.generate_preview import generate_migration_preview

KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "knowledge"


@pytest.fixture
def knowledge():
    return load_knowledge(KNOWLEDGE_DIR)


@pytest.fixture
def infra_simple(tmp_path):
    """Simple infra: 2 primary resources, no DB, no AI."""
    (tmp_path / "gcp-resource-inventory.json").write_text(json.dumps({
        "resources": [
            {"address": "google_cloud_run_service.api", "type": "google_cloud_run_service", "classification": "PRIMARY"},
            {"address": "google_storage_bucket.assets", "type": "google_storage_bucket", "classification": "PRIMARY"},
            {"address": "google_compute_network.vpc", "type": "google_compute_network", "classification": "SECONDARY"},
        ]
    }))
    return tmp_path


@pytest.fixture
def infra_complex(tmp_path):
    """Complex infra: many resources + BigQuery."""
    resources = [
        {"address": f"google_compute_instance.web{i}", "type": "google_compute_instance", "classification": "PRIMARY"}
        for i in range(10)
    ]
    resources.append({"address": "google_bigquery_dataset.analytics", "type": "google_bigquery_dataset", "classification": "PRIMARY"})
    (tmp_path / "gcp-resource-inventory.json").write_text(json.dumps({"resources": resources}))
    return tmp_path


@pytest.fixture
def ai_only(tmp_path):
    """AI-only: no inventory, just ai-workload-profile."""
    (tmp_path / "ai-workload-profile.json").write_text(json.dumps({
        "summary": {"ai_source": "openai", "total_models_detected": 2},
        "models": [
            {"model_id": "gpt-4o", "service": "OpenAI"},
            {"model_id": "text-embedding-3-small", "service": "OpenAI"},
        ],
        "integration": {"gateway_type": "direct", "capabilities_summary": {"text_generation": True, "embeddings": True}},
    }))
    return tmp_path


@pytest.fixture
def hybrid(tmp_path):
    """Infra + AI profile."""
    (tmp_path / "gcp-resource-inventory.json").write_text(json.dumps({
        "resources": [
            {"address": "google_cloud_run_service.api", "type": "google_cloud_run_service", "classification": "PRIMARY"},
            {"address": "google_sql_database_instance.db", "type": "google_sql_database_instance", "classification": "PRIMARY"},
        ]
    }))
    (tmp_path / "ai-workload-profile.json").write_text(json.dumps({
        "summary": {"ai_source": "gemini", "total_models_detected": 1},
        "models": [{"model_id": "gemini-2.5-flash", "service": "Vertex AI"}],
        "integration": {"gateway_type": None, "capabilities_summary": {"text_generation": True}},
    }))
    return tmp_path


class TestNoArtifacts:
    def test_empty_dir(self, tmp_path, knowledge):
        result = generate_migration_preview(str(tmp_path), knowledge)
        assert result["status"] == "skipped"

    def test_missing_dir(self, knowledge):
        result = generate_migration_preview("/nonexistent/path", knowledge)
        assert result["status"] == "error"


class TestInfraRoute:
    def test_simple_infra(self, infra_simple, knowledge):
        result = generate_migration_preview(str(infra_simple), knowledge)
        assert result["status"] == "ok"
        p = result["preview"]
        assert p["route"] == "infra"
        assert p["complexity_signal"] == "likely_simple"
        assert p["primary_resource_count"] == 2
        assert p["eligible_for_clarify_fast_path"] is True
        assert p["ai_detected"] is False

    def test_complex_infra(self, infra_complex, knowledge):
        result = generate_migration_preview(str(infra_complex), knowledge)
        p = result["preview"]
        assert p["complexity_signal"] == "complex"
        assert p["eligible_for_clarify_fast_path"] is False

    def test_cost_preview(self, infra_simple, knowledge):
        result = generate_migration_preview(str(infra_simple), knowledge)
        p = result["preview"]
        assert p["cost_preview"] is not None
        assert p["cost_preview"]["aws_monthly_range_usd"]["low"] > 0
        assert p["cost_preview"]["aws_monthly_range_usd"]["high"] > p["cost_preview"]["aws_monthly_range_usd"]["low"]
        assert p["cost_preview"]["gcp_monthly_usd"] is None  # No billing data

    def test_with_billing(self, infra_simple, knowledge):
        (infra_simple / "billing-profile.json").write_text(json.dumps({
            "summary": {"total_monthly_spend": 450.00, "service_count": 3, "currency": "USD"}
        }))
        result = generate_migration_preview(str(infra_simple), knowledge)
        p = result["preview"]
        assert p["cost_preview"]["gcp_monthly_usd"] == 450.00

    def test_services_summary(self, infra_simple, knowledge):
        result = generate_migration_preview(str(infra_simple), knowledge)
        p = result["preview"]
        targets = {s["typical_aws_target"] for s in p["services_summary"]}
        assert "Fargate" in targets
        assert "S3" in targets

    def test_writes_file(self, infra_simple, knowledge):
        generate_migration_preview(str(infra_simple), knowledge)
        assert (infra_simple / "migration-preview.json").exists()


class TestAIOnlyRoute:
    def test_ai_only_route(self, ai_only, knowledge):
        result = generate_migration_preview(str(ai_only), knowledge)
        p = result["preview"]
        assert p["route"] == "ai_only"
        assert p["primary_resource_count"] == 0
        assert p["ai_detected"] is True
        assert p["eligible_for_clarify_fast_path"] is False

    def test_bedrock_mapping(self, ai_only, knowledge):
        result = generate_migration_preview(str(ai_only), knowledge)
        p = result["preview"]
        targets = p["ai_summary"]["bedrock_targets"]
        assert len(targets) == 2
        assert targets[0]["bedrock_equivalent"] == "Claude Sonnet 4.6"
        assert targets[1]["bedrock_equivalent"] == "Amazon Titan Embeddings v2"

    def test_cost_direction(self, ai_only, knowledge):
        result = generate_migration_preview(str(ai_only), knowledge)
        targets = result["preview"]["ai_summary"]["bedrock_targets"]
        # gpt-4o → Claude Sonnet: 2.50 input vs 3.00 = higher
        assert targets[0]["cost_direction"] == "higher"


class TestHybridRoute:
    def test_hybrid_uses_infra_route(self, hybrid, knowledge):
        result = generate_migration_preview(str(hybrid), knowledge)
        p = result["preview"]
        assert p["route"] == "infra"
        assert p["ai_detected"] is True
        assert p["eligible_for_clarify_fast_path"] is False  # AI detected

    def test_hybrid_decisions(self, hybrid, knowledge):
        result = generate_migration_preview(str(hybrid), knowledge)
        p = result["preview"]
        decisions = p["key_decisions_ahead"]
        assert any("region" in d.lower() for d in decisions)
        assert any("Bedrock" in d for d in decisions)


class TestTimelineHint:
    def test_simple_infra_timeline(self, infra_simple, knowledge):
        result = generate_migration_preview(str(infra_simple), knowledge)
        assert "3-6 weeks" in result["preview"]["timeline_hint"]

    def test_ai_only_timeline(self, ai_only, knowledge):
        result = generate_migration_preview(str(ai_only), knowledge)
        assert "weeks" in result["preview"]["timeline_hint"]
