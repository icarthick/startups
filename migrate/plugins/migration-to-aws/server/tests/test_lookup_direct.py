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
    assert result["type"] == "direct"
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


# --- Specialist gate (deferred) ---

def test_bigquery_dataset_deferred(knowledge):
    """google_bigquery_dataset → deferred specialist engagement."""
    result = lookup_direct_mapping("google_bigquery_dataset", knowledge=knowledge)
    assert result["hit"] is True
    assert result["type"] == "deferred"
    assert result["aws_service"] == "Deferred — specialist engagement"
    assert result["human_expertise_required"] is True


def test_bigquery_table_deferred(knowledge):
    """google_bigquery_table → deferred."""
    result = lookup_direct_mapping("google_bigquery_table", knowledge=knowledge)
    assert result["hit"] is True
    assert result["type"] == "deferred"


def test_bigquery_ml_deferred(knowledge):
    """google_bigquery_ml_model → deferred (prefix match)."""
    result = lookup_direct_mapping("google_bigquery_ml_model", knowledge=knowledge)
    assert result["hit"] is True
    assert result["type"] == "deferred"


# --- Skip mappings ---

def test_identity_platform_skip(knowledge):
    """google_identity_platform_* → skip (auth provider, keep existing)."""
    result = lookup_direct_mapping("google_identity_platform_config", knowledge=knowledge)
    assert result["hit"] is True
    assert result["type"] == "skip"
    assert "auth" in result["reason"].lower()


def test_monitoring_skip(knowledge):
    """google_monitoring_alert → skip (wildcard match)."""
    result = lookup_direct_mapping("google_monitoring_alert_policy", knowledge=knowledge)
    assert result["hit"] is True
    assert result["type"] == "skip"


def test_logging_skip(knowledge):
    """google_logging_metric → skip."""
    result = lookup_direct_mapping("google_logging_metric", knowledge=knowledge)
    assert result["hit"] is True
    assert result["type"] == "skip"


# --- Auto-extraction from raw_config ---

def test_cloud_sql_sqlserver_auto_extracted(knowledge):
    """raw_config with SQLSERVER database_version → auto-extracts engine, hits direct mapping."""
    result = lookup_direct_mapping(
        "google_sql_database_instance",
        raw_config={"database_version": "SQLSERVER_2019_STANDARD", "settings": {}},
        knowledge=knowledge,
    )
    assert result["hit"] is True
    assert result["aws_service"] == "RDS SQL Server"


def test_cloud_sql_postgres_no_direct_hit(knowledge):
    """raw_config with POSTGRES → auto-extracts engine=postgres, no direct mapping (goes to recommend)."""
    result = lookup_direct_mapping(
        "google_sql_database_instance",
        raw_config={"database_version": "POSTGRES_15", "settings": {}},
        knowledge=knowledge,
    )
    assert result["hit"] is False


def test_cloud_sql_mysql_no_direct_hit(knowledge):
    """raw_config with MYSQL → no direct mapping."""
    result = lookup_direct_mapping(
        "google_sql_database_instance",
        raw_config={"database_version": "MYSQL_8_0", "settings": {}},
        knowledge=knowledge,
    )
    assert result["hit"] is False


def test_raw_config_no_extractor(knowledge):
    """Non-SQL resource with raw_config → no extraction attempted, works normally."""
    result = lookup_direct_mapping(
        "google_storage_bucket",
        raw_config={"location": "US", "versioning": {"enabled": True}},
        knowledge=knowledge,
    )
    assert result["hit"] is True
    assert result["aws_service"] == "S3"
