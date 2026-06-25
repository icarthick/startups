"""Unit tests for detect_ai_signals and cluster_terraform."""

import json
from pathlib import Path

import pytest

from migration_orchestrator.knowledge import load_knowledge
from migration_orchestrator.tools.detect_ai_signals import detect_ai_signals
from migration_orchestrator.tools.cluster_terraform import cluster_terraform

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


def test_bidirectional_serves(knowledge):
    """PRIMARY referencing a SECONDARY → secondary serves that primary."""
    resources = [
        {"address": "google_container_cluster.primary", "type": "google_container_cluster", "name": "primary",
         "config": {}, "depends_on": ["google_service_account.gke"]},
        {"address": "google_service_account.gke", "type": "google_service_account", "name": "gke",
         "config": {}, "depends_on": []},
    ]
    result = cluster_terraform(resources, knowledge=knowledge)
    res_map = {r["address"]: r for r in result["resources"]}
    assert "google_container_cluster.primary" in res_map["google_service_account.gke"].get("serves", [])


def test_transitive_serves_via_iam(knowledge):
    """IAM binding links SA to primary → SA serves that primary transitively."""
    resources = [
        {"address": "google_sql_database_instance.db", "type": "google_sql_database_instance", "name": "db",
         "config": {}, "depends_on": []},
        {"address": "google_service_account.app", "type": "google_service_account", "name": "app",
         "config": {}, "depends_on": []},
        {"address": "google_project_iam_member.app_sql", "type": "google_project_iam_member", "name": "app_sql",
         "config": {}, "depends_on": []},
    ]
    edges = [
        {"from": "google_project_iam_member.app_sql", "to": "google_service_account.app", "type": "reference"},
        {"from": "google_project_iam_member.app_sql", "to": "google_sql_database_instance.db", "type": "reference"},
    ]
    result = cluster_terraform(resources, edges=edges, knowledge=knowledge)
    res_map = {r["address"]: r for r in result["resources"]}
    assert "google_sql_database_instance.db" in res_map["google_service_account.app"].get("serves", [])


def test_external_edges_used(knowledge):
    """Edges passed as parameter are used for serves resolution."""
    resources = [
        {"address": "google_cloud_run_service.api", "type": "google_cloud_run_service", "name": "api",
         "config": {}, "depends_on": []},
        {"address": "google_service_account.api_sa", "type": "google_service_account", "name": "api_sa",
         "config": {}, "depends_on": []},
    ]
    edges = [
        {"from": "google_cloud_run_service.api", "to": "google_service_account.api_sa", "type": "reference"},
    ]
    result = cluster_terraform(resources, edges=edges, knowledge=knowledge)
    res_map = {r["address"]: r for r in result["resources"]}
    assert "google_cloud_run_service.api" in res_map["google_service_account.api_sa"].get("serves", [])


# --- create_ai_profile_from_iac ---

from migration_orchestrator.tools.create_ai_profile import create_ai_profile_from_iac


def test_creates_ai_profile_gemini(tmp_path):
    """Writes ai-workload-profile.json with ai_source=gemini."""
    ai_detection = {"confidence": 0.95, "confidence_level": "very_high", "signals_found": [{"resource": "google_vertex_ai_endpoint.x", "pattern": "google_vertex_ai_*", "confidence": 0.95}], "ai_services": ["vertex_ai"]}
    vertex_resources = [{"address": "google_vertex_ai_endpoint.x", "type": "google_vertex_ai_endpoint", "config": {}}]

    result = create_ai_profile_from_iac(
        ai_source="gemini", ai_detection=ai_detection,
        vertex_resources=vertex_resources, migration_dir=str(tmp_path),
    )
    assert result["status"] == "written"
    assert (tmp_path / "ai-workload-profile.json").exists()

    import json
    profile = json.loads((tmp_path / "ai-workload-profile.json").read_text())
    assert profile["metadata"]["profile_source"] == "iac_vertex"
    assert profile["summary"]["ai_source"] == "gemini"
    assert profile["summary"]["overall_confidence"] == 0.95
    assert profile["summary"]["inferred_from_iac"] is True
    assert len(profile["infrastructure"]) == 1
    assert len(profile["detection_signals"]) == 1


def test_creates_ai_profile_other(tmp_path):
    """Writes ai-workload-profile.json with ai_source=other for traditional ML."""
    ai_detection = {"confidence": 0.95, "confidence_level": "very_high", "signals_found": [{"resource": "google_vertex_ai_custom_job.train", "pattern": "google_vertex_ai_*", "confidence": 0.95}], "ai_services": ["vertex_ai"]}
    vertex_resources = [{"address": "google_vertex_ai_custom_job.train", "type": "google_vertex_ai_custom_job", "config": {}}]

    result = create_ai_profile_from_iac(
        ai_source="other", ai_detection=ai_detection,
        vertex_resources=vertex_resources, migration_dir=str(tmp_path),
    )
    profile = json.loads((tmp_path / "ai-workload-profile.json").read_text())
    assert profile["summary"]["ai_source"] == "other"
    assert profile["models"] == []
    assert profile["integration"]["primary_sdk"] is None
