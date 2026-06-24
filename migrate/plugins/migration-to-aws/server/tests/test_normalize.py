"""Unit tests for normalize_resource."""

from pathlib import Path

import pytest

from migration_tools.knowledge import load_knowledge
from migration_tools.tools.normalize import normalize_resource

KNOWLEDGE_DIR = Path(__file__).resolve().parents[1].parent / "knowledge"


@pytest.fixture(scope="module")
def knowledge():
    return load_knowledge(KNOWLEDGE_DIR)


# --- Cloud SQL ---

def test_cloud_sql_postgres(knowledge):
    """Cloud SQL Postgres → relational-db, engine=postgres, availability from config."""
    result = normalize_resource(
        source_type="google_sql_database_instance",
        raw_config={
            "database_version": "POSTGRES_15",
            "settings": {"tier": "db-f1-micro", "availability_type": "REGIONAL"},
        },
        knowledge=knowledge,
    )
    assert result["archetype"] == "relational-db"
    assert result["canonical_fields"]["engine"] == "postgres"
    assert result["canonical_fields"]["availability"] == "multi-az"
    assert result["canonical_fields"]["size_class"] == "micro"


def test_cloud_sql_mysql(knowledge):
    """Cloud SQL MySQL → engine=mysql."""
    result = normalize_resource(
        source_type="google_sql_database_instance",
        raw_config={
            "database_version": "MYSQL_8_0",
            "settings": {"tier": "db-g1-small", "availability_type": "ZONAL"},
        },
        knowledge=knowledge,
    )
    assert result["canonical_fields"]["engine"] == "mysql"
    assert result["canonical_fields"]["availability"] == "single-az"
    assert result["canonical_fields"]["size_class"] == "small"


def test_cloud_sql_sqlserver(knowledge):
    """Cloud SQL SQL Server → engine=sqlserver."""
    result = normalize_resource(
        source_type="google_sql_database_instance",
        raw_config={
            "database_version": "SQLSERVER_2019_STANDARD",
            "settings": {"tier": "db-custom-2-7680", "availability_type": "REGIONAL"},
        },
        knowledge=knowledge,
    )
    assert result["canonical_fields"]["engine"] == "sqlserver"
    assert result["canonical_fields"]["size_class"] == "medium"


def test_cloud_sql_missing_availability(knowledge):
    """Missing availability_type → requires_inference."""
    result = normalize_resource(
        source_type="google_sql_database_instance",
        raw_config={
            "database_version": "POSTGRES_15",
            "settings": {"tier": "db-f1-micro"},
        },
        knowledge=knowledge,
    )
    assert result["canonical_fields"]["engine"] == "postgres"
    assert "availability" in result["requires_inference"]


# --- Cloud Run ---

def test_cloud_run(knowledge):
    """Cloud Run → container workload with timeout/memory/vcpu extracted."""
    result = normalize_resource(
        source_type="google_cloud_run_service",
        raw_config={
            "template": {
                "spec": {
                    "timeout_seconds": 300,
                    "containers": [{"resources": {"limits": {"memory": "512Mi", "cpu": "1"}}}],
                }
            }
        },
        knowledge=knowledge,
    )
    assert result["archetype"] == "container"
    assert result["canonical_fields"]["service_type"] == "container"
    assert result["canonical_fields"]["timeout_seconds"] == 300
    assert "workload_pattern" in result["requires_inference"]


# --- Compute Engine ---

def test_compute_engine_e2_medium(knowledge):
    """Compute Engine e2-medium → vm, vcpu=2, memory=4."""
    result = normalize_resource(
        source_type="google_compute_instance",
        raw_config={"machine_type": "e2-medium"},
        knowledge=knowledge,
    )
    assert result["archetype"] == "vm"
    assert result["canonical_fields"]["service_type"] == "vm"
    assert result["canonical_fields"]["vcpu"] == 2
    assert result["canonical_fields"]["memory_gb"] == 4
    assert "workload_pattern" in result["requires_inference"]


def test_compute_engine_with_gpu(knowledge):
    """Compute Engine with GPU → gpu=true."""
    result = normalize_resource(
        source_type="google_compute_instance",
        raw_config={"machine_type": "n2-standard-4", "guest_accelerator": [{"type": "nvidia-tesla-t4"}]},
        knowledge=knowledge,
    )
    assert result["canonical_fields"]["gpu"] is True


# --- GKE ---

def test_gke(knowledge):
    """GKE → kubernetes workload."""
    result = normalize_resource(
        source_type="google_container_cluster",
        raw_config={"name": "my-cluster"},
        knowledge=knowledge,
    )
    assert result["archetype"] == "kubernetes"
    assert result["canonical_fields"]["service_type"] == "kubernetes"


# --- Firestore ---

def test_firestore(knowledge):
    """Firestore → nosql-document workload."""
    result = normalize_resource(
        source_type="google_firestore_database",
        raw_config={"name": "my-db", "type": "FIRESTORE_NATIVE"},
        knowledge=knowledge,
    )
    assert result["archetype"] == "nosql-document"


# --- Unknown source type ---

def test_unknown_source_type(knowledge):
    """Unknown source type → error."""
    result = normalize_resource(
        source_type="google_unknown_resource",
        raw_config={"foo": "bar"},
        knowledge=knowledge,
    )
    assert result["archetype"] is None
    assert "error" in result
