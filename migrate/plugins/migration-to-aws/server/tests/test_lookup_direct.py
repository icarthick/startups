"""Unit tests for lookup_direct_mapping."""

from pathlib import Path

import pytest

from migration_tools.knowledge import load_knowledge
from migration_tools.tools.lookup_direct import lookup_direct_mapping

KNOWLEDGE_DIR = Path(__file__).resolve().parents[1].parent / "knowledge"


@pytest.fixture(scope="module")
def knowledge():
    return load_knowledge(KNOWLEDGE_DIR)


# --- Hits (unconditional) ---

def test_gcs_hit(knowledge):
    result = lookup_direct_mapping("google_storage_bucket", knowledge=knowledge)
    assert result["hit"] is True
    assert result["aws_service"] == "S3"
    assert result["confidence"] == "deterministic"


def test_vpc_hit(knowledge):
    result = lookup_direct_mapping("google_compute_network", knowledge=knowledge)
    assert result["hit"] is True
    assert result["aws_service"] == "VPC"


def test_firewall_hit(knowledge):
    result = lookup_direct_mapping("google_compute_firewall", knowledge=knowledge)
    assert result["hit"] is True
    assert result["aws_service"] == "Security Group"


def test_redis_hit(knowledge):
    result = lookup_direct_mapping("google_redis_instance", knowledge=knowledge)
    assert result["hit"] is True
    assert result["aws_service"] == "ElastiCache Redis"


def test_secrets_hit(knowledge):
    result = lookup_direct_mapping("google_secret_manager_secret", knowledge=knowledge)
    assert result["hit"] is True
    assert result["aws_service"] == "Secrets Manager"


# --- Conditional hit (SQL Server) ---

def test_sqlserver_conditional_hit(knowledge):
    result = lookup_direct_mapping(
        "google_sql_database_instance",
        condition_context={"engine": "sqlserver"},
        knowledge=knowledge,
    )
    assert result["hit"] is True
    assert result["aws_service"] == "RDS SQL Server"


def test_postgres_conditional_miss(knowledge):
    """Postgres doesn't match the sqlserver condition → miss."""
    result = lookup_direct_mapping(
        "google_sql_database_instance",
        condition_context={"engine": "postgres"},
        knowledge=knowledge,
    )
    assert result["hit"] is False


def test_sql_no_context_miss(knowledge):
    """SQL instance without condition_context → miss (can't evaluate condition)."""
    result = lookup_direct_mapping(
        "google_sql_database_instance",
        knowledge=knowledge,
    )
    assert result["hit"] is False


# --- Misses ---

def test_cloud_run_miss(knowledge):
    """Cloud Run is NOT in direct mappings (has eliminators)."""
    result = lookup_direct_mapping("google_cloud_run_service", knowledge=knowledge)
    assert result["hit"] is False


def test_compute_instance_miss(knowledge):
    """Compute Engine is NOT in direct mappings."""
    result = lookup_direct_mapping("google_compute_instance", knowledge=knowledge)
    assert result["hit"] is False


def test_unknown_type_miss(knowledge):
    result = lookup_direct_mapping("google_unknown_thing", knowledge=knowledge)
    assert result["hit"] is False
