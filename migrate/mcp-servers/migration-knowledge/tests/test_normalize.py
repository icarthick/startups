"""Unit tests for normalize_resource."""

from pathlib import Path

import pytest

from migration_knowledge.knowledge import load_knowledge
from migration_knowledge.tools.normalize import normalize_resource

KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "knowledge"


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
    assert result["archetype"] == "container"
    assert result["canonical_fields"]["service_type"] == "container"


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


# --- Parent-ref (node pool) scenarios ---

def test_node_pool_parent_fargate_skip(knowledge):
    """Node pool + parent resolved to Fargate → skip mapping."""
    result = normalize_resource(
        source_type="google_container_node_pool",
        raw_config={"machine_type": "e2-standard-4", "autoscaling": {"min_node_count": 1, "max_node_count": 5}},
        knowledge=knowledge,
        resolved_primaries=[{"type": "google_container_cluster", "aws_service": "Fargate"}],
    )
    assert result["next_action"] == "skip"
    assert result["archetype"] == "container-node-group"
    assert "Fargate" in result["skip_reason"]


def test_node_pool_parent_eks_proceed(knowledge):
    """Node pool + parent resolved to EKS → proceed with field extraction."""
    result = normalize_resource(
        source_type="google_container_node_pool",
        raw_config={
            "machine_type": "n1-highmem-8",
            "guest_accelerator": {"type": "nvidia-tesla-v100", "count": 4},
            "autoscaling": {"min_node_count": 0, "max_node_count": 4},
        },
        knowledge=knowledge,
        resolved_primaries=[{"type": "google_container_cluster", "aws_service": "EKS"}],
    )
    assert result["archetype"] == "container-node-group"
    assert result["next_tool"] == "recommend_compute"
    assert result["canonical_fields"]["service_type"] == "vm"
    assert result["canonical_fields"]["vcpu"] == 8
    assert result["canonical_fields"]["memory_gb"] == 52
    assert result["canonical_fields"]["gpu"] is True
    assert result["parent"]["aws_service"] == "EKS"
    assert result["parent"]["status"] == "resolved"


def test_node_pool_parent_ec2_proceed(knowledge):
    """Node pool + parent resolved to EC2 → proceed."""
    result = normalize_resource(
        source_type="google_container_node_pool",
        raw_config={"machine_type": "e2-standard-4", "autoscaling": {"min_node_count": 2, "max_node_count": 10}},
        knowledge=knowledge,
        resolved_primaries=[{"type": "google_container_cluster", "aws_service": "EC2"}],
    )
    assert result["next_tool"] == "recommend_compute"
    assert result["canonical_fields"]["vcpu"] == 4
    assert result["canonical_fields"]["memory_gb"] == 16


def test_node_pool_no_primaries_provided(knowledge):
    """Node pool + no resolved_primaries → proceeds (no parent info, defers to LLM)."""
    result = normalize_resource(
        source_type="google_container_node_pool",
        raw_config={"machine_type": "e2-standard-4", "autoscaling": {"min_node_count": 1, "max_node_count": 5}},
        knowledge=knowledge,
        resolved_primaries=None,
    )
    assert result["archetype"] == "container-node-group"
    assert result["next_tool"] == "recommend_compute"
    assert result["parent"]["status"] == "not_provided"


def test_node_pool_parent_not_found(knowledge):
    """Node pool + primaries without a container cluster → not_found status."""
    result = normalize_resource(
        source_type="google_container_node_pool",
        raw_config={"machine_type": "e2-standard-4", "autoscaling": {"min_node_count": 1, "max_node_count": 5}},
        knowledge=knowledge,
        resolved_primaries=[{"type": "google_compute_network", "aws_service": "VPC"}],
    )
    assert result["next_tool"] == "recommend_compute"
    assert result["parent"]["status"] == "not_found"


def test_node_pool_ambiguous_parents(knowledge):
    """Node pool + two container clusters in primaries → ambiguous."""
    result = normalize_resource(
        source_type="google_container_node_pool",
        raw_config={"machine_type": "e2-standard-4", "autoscaling": {"min_node_count": 1, "max_node_count": 5}},
        knowledge=knowledge,
        resolved_primaries=[
            {"type": "google_container_cluster", "aws_service": "EKS"},
            {"type": "google_container_cluster", "aws_service": "Fargate"},
        ],
    )
    assert result["next_tool"] == "recommend_compute"
    assert result["parent"]["status"] == "ambiguous"
    assert len(result["parent"]["candidates"]) == 2
