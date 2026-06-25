"""Unit tests for detect_ai_signals and cluster_terraform."""

from pathlib import Path

import pytest

from migration_knowledge.knowledge import load_knowledge
from migration_knowledge.tools.detect_ai_signals import detect_ai_signals
from migration_knowledge.tools.cluster_terraform import cluster_terraform

KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "knowledge"


@pytest.fixture(scope="module")
def knowledge():
    return load_knowledge(KNOWLEDGE_DIR)


# --- detect_ai_signals ---

def test_ai_vertex_detected():
    """Vertex AI resource → has_ai_workload=True, high confidence."""
    resources = [
        {"address": "google_vertex_ai_endpoint.serving", "type": "google_vertex_ai_endpoint", "name": "serving"},
    ]
    result = detect_ai_signals(resources)
    assert result["has_ai_workload"] is True
    assert result["confidence"] == 0.95
    assert "vertex_ai" in result["ai_services"]


def test_ai_name_keyword():
    """Module name with 'ml' → signal detected."""
    resources = [
        {"address": "module.ml_pipeline", "type": "module", "name": "ml_pipeline"},
    ]
    result = detect_ai_signals(resources)
    assert len(result["signals_found"]) > 0
    assert result["signals_found"][0]["confidence"] == 0.70


def test_no_ai_signals():
    """Regular infra → no AI detected."""
    resources = [
        {"address": "google_compute_instance.web", "type": "google_compute_instance", "name": "web"},
        {"address": "google_storage_bucket.data", "type": "google_storage_bucket", "name": "data"},
    ]
    result = detect_ai_signals(resources)
    assert result["has_ai_workload"] is False
    assert result["confidence"] == 0.0


def test_ai_multiple_services():
    """Multiple AI services detected."""
    resources = [
        {"address": "google_vertex_ai_model.m", "type": "google_vertex_ai_model", "name": "m"},
        {"address": "google_cloud_document_ai_processor.p", "type": "google_cloud_document_ai_processor", "name": "p"},
    ]
    result = detect_ai_signals(resources)
    assert "vertex_ai" in result["ai_services"]
    assert "document_ai" in result["ai_services"]


# --- cluster_terraform ---

def test_basic_classification(knowledge):
    """Cloud Run → PRIMARY/compute, service_account → SECONDARY/identity."""
    resources = [
        {"address": "google_cloud_run_service.api", "type": "google_cloud_run_service", "name": "api", "config": {}, "depends_on": []},
        {"address": "google_service_account.app", "type": "google_service_account", "name": "app", "config": {}, "depends_on": []},
    ]
    result = cluster_terraform(resources, knowledge=knowledge)
    res_map = {r["address"]: r for r in result["resources"]}

    assert res_map["google_cloud_run_service.api"]["classification"] == "PRIMARY"
    assert res_map["google_cloud_run_service.api"]["tier"] == "compute"
    assert res_map["google_service_account.app"]["classification"] == "SECONDARY"
    assert res_map["google_service_account.app"]["secondary_role"] == "identity"


def test_excluded_resources(knowledge):
    """Identity Platform → excluded from output."""
    resources = [
        {"address": "google_identity_platform_config.auth", "type": "google_identity_platform_config", "name": "auth", "config": {}, "depends_on": []},
        {"address": "google_compute_instance.web", "type": "google_compute_instance", "name": "web", "config": {}, "depends_on": []},
    ]
    result = cluster_terraform(resources, knowledge=knowledge)
    addresses = [r["address"] for r in result["resources"]]
    assert "google_identity_platform_config.auth" not in addresses
    assert "google_compute_instance.web" in addresses
    assert result["summary"]["excluded_resources"] == 1


def test_depth_assignment(knowledge):
    """Resources with dependencies get higher depth."""
    resources = [
        {"address": "google_compute_network.vpc", "type": "google_compute_network", "name": "vpc", "config": {}, "depends_on": []},
        {"address": "google_cloud_run_service.api", "type": "google_cloud_run_service", "name": "api", "config": {}, "depends_on": ["google_compute_network.vpc"]},
    ]
    result = cluster_terraform(resources, knowledge=knowledge)
    res_map = {r["address"]: r for r in result["resources"]}

    assert res_map["google_compute_network.vpc"]["depth"] == 0
    assert res_map["google_cloud_run_service.api"]["depth"] == 1


def test_clustering_produces_clusters(knowledge):
    """Resources get grouped into clusters."""
    resources = [
        {"address": "google_compute_network.vpc", "type": "google_compute_network", "name": "vpc", "config": {}, "depends_on": []},
        {"address": "google_cloud_run_service.api", "type": "google_cloud_run_service", "name": "api", "config": {}, "depends_on": []},
        {"address": "google_sql_database_instance.db", "type": "google_sql_database_instance", "name": "db", "config": {}, "depends_on": []},
    ]
    result = cluster_terraform(resources, knowledge=knowledge)
    assert result["summary"]["total_clusters"] >= 2  # networking + at least one other
    assert all("cluster_id" in r for r in result["resources"])


def test_networking_cluster_groups_together(knowledge):
    """VPC + firewall → same networking cluster."""
    resources = [
        {"address": "google_compute_network.vpc", "type": "google_compute_network", "name": "vpc", "config": {}, "depends_on": []},
        {"address": "google_compute_firewall.allow", "type": "google_compute_firewall", "name": "allow", "config": {}, "depends_on": ["google_compute_network.vpc"]},
    ]
    result = cluster_terraform(resources, knowledge=knowledge)
    res_map = {r["address"]: r for r in result["resources"]}
    assert res_map["google_compute_network.vpc"]["cluster_id"] == res_map["google_compute_firewall.allow"]["cluster_id"]


def test_same_type_grouping(knowledge):
    """Two Cloud Run services → same cluster."""
    resources = [
        {"address": "google_cloud_run_service.api", "type": "google_cloud_run_service", "name": "api", "config": {}, "depends_on": []},
        {"address": "google_cloud_run_service.worker", "type": "google_cloud_run_service", "name": "worker", "config": {}, "depends_on": []},
    ]
    result = cluster_terraform(resources, knowledge=knowledge)
    res_map = {r["address"]: r for r in result["resources"]}
    assert res_map["google_cloud_run_service.api"]["cluster_id"] == res_map["google_cloud_run_service.worker"]["cluster_id"]


def test_summary_counts(knowledge):
    """Summary has correct counts."""
    resources = [
        {"address": "google_cloud_run_service.api", "type": "google_cloud_run_service", "name": "api", "config": {}, "depends_on": []},
        {"address": "google_service_account.sa", "type": "google_service_account", "name": "sa", "config": {}, "depends_on": []},
        {"address": "google_identity_platform_config.x", "type": "google_identity_platform_config", "name": "x", "config": {}, "depends_on": []},
    ]
    result = cluster_terraform(resources, knowledge=knowledge)
    assert result["summary"]["primary_resources"] == 1
    assert result["summary"]["secondary_resources"] == 1
    assert result["summary"]["excluded_resources"] == 1
    assert result["summary"]["total_resources"] == 2


def test_writes_files_when_migration_dir_provided(tmp_path, knowledge):
    """With migration_dir, writes inventory and clusters JSON files."""
    resources = [
        {"address": "google_cloud_run_service.api", "type": "google_cloud_run_service", "name": "api", "config": {}, "depends_on": []},
        {"address": "google_compute_network.vpc", "type": "google_compute_network", "name": "vpc", "config": {}, "depends_on": []},
    ]
    ai_detection = {"has_ai_workload": False, "confidence": 0, "confidence_level": "none", "signals_found": [], "ai_services": []}
    metadata = {"report_date": "2026-06-25", "project_directory": "/test"}

    result = cluster_terraform(
        resources, migration_dir=str(tmp_path), ai_detection=ai_detection,
        metadata=metadata, knowledge=knowledge,
    )

    assert "files_written" in result
    assert (tmp_path / "gcp-resource-inventory.json").exists()
    assert (tmp_path / "gcp-resource-clusters.json").exists()

    # Verify inventory has correct schema
    import json
    inventory = json.loads((tmp_path / "gcp-resource-inventory.json").read_text())
    assert inventory["metadata"]["report_date"] == "2026-06-25"
    assert inventory["summary"]["total_resources"] == 2
    assert "ai_detection" in inventory
    assert all("address" in r and "classification" in r and "depth" in r for r in inventory["resources"])

    # Verify clusters file
    clusters = json.loads((tmp_path / "gcp-resource-clusters.json").read_text())
    assert len(clusters["clusters"]) >= 1


def test_no_files_without_migration_dir(knowledge):
    """Without migration_dir, returns data only (no file writing)."""
    resources = [
        {"address": "google_cloud_run_service.api", "type": "google_cloud_run_service", "name": "api", "config": {}, "depends_on": []},
    ]
    result = cluster_terraform(resources, knowledge=knowledge)
    assert "files_written" not in result
    assert "resources" in result
    assert "clusters" in result
