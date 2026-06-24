"""Unit tests for recommend_database_target.

Each test case corresponds to an example from the original database.md rubric
or a boundary condition identified during design.
"""

import json
from pathlib import Path

import pytest

from migration_tools.knowledge import load_knowledge
from migration_tools.tools.recommend_database import recommend_database_target

KNOWLEDGE_DIR = Path(__file__).resolve().parents[1].parent / "knowledge"


@pytest.fixture(scope="module")
def knowledge():
    return load_knowledge(KNOWLEDGE_DIR)


# --- Happy path: Postgres on RDS ---

def test_postgres_single_az_micro_low(knowledge):
    """Example 1 from database.md: Cloud SQL Postgres, dev/low HA."""
    result = recommend_database_target(
        engine="postgres", availability="single-az", size_class="micro",
        io_workload="low", traffic="steady", knowledge=knowledge,
    )
    assert result["aws_service"] == "RDS PostgreSQL"
    assert result["aws_config"]["instance_class"] == "db.t4g.micro"
    assert result["aws_config"]["multi_az"] is False
    assert result["aws_config"]["storage_type"] == "gp3"
    assert result["confidence"] == "inferred"


def test_postgres_multi_az_read_heavy(knowledge):
    """Example 4: Cloud SQL Postgres, production Multi-AZ, read-heavy."""
    result = recommend_database_target(
        engine="postgres", availability="multi-az", size_class="medium",
        io_workload="medium", traffic="read-heavy", knowledge=knowledge,
    )
    assert result["aws_service"] == "RDS PostgreSQL"
    assert result["aws_config"]["multi_az"] is True
    assert result["aws_config"]["read_replica"] is True
    assert result["aws_config"]["replica_type"] == "read-replica"


def test_postgres_multi_az_high_io(knowledge):
    """High I/O on RDS → io2 storage."""
    result = recommend_database_target(
        engine="postgres", availability="multi-az", size_class="large",
        io_workload="high", traffic="steady", knowledge=knowledge,
    )
    assert result["aws_service"] == "RDS PostgreSQL"
    assert result["aws_config"]["storage_type"] == "io2"
    assert result["aws_config"]["instance_class"] == "db.r6g.large"


# --- Happy path: Postgres on Aurora ---

def test_postgres_multi_az_ha_high_io(knowledge):
    """Example 5: mission-critical, high I/O → Aurora I/O-Optimized."""
    result = recommend_database_target(
        engine="postgres", availability="multi-az-ha", size_class="large",
        io_workload="high", traffic="steady", knowledge=knowledge,
    )
    assert result["aws_service"] == "Aurora PostgreSQL"
    assert result["aws_config"]["multi_az"] is True
    assert result["aws_config"]["storage_type"] == "io-optimized"
    assert result["aws_config"]["instance_class"] == "db.r6g.large"


def test_postgres_aurora_spiky_serverless(knowledge):
    """Spiky traffic on Aurora → Serverless v2 with ACU."""
    result = recommend_database_target(
        engine="postgres", availability="multi-az-ha", size_class="medium",
        io_workload="low", traffic="spiky", knowledge=knowledge,
    )
    assert result["aws_service"] == "Aurora PostgreSQL"
    assert result["aws_config"]["instance_class"] is None
    assert result["aws_config"]["min_acu"] == 1
    assert result["aws_config"]["max_acu"] == 16
    assert result["aws_config"]["storage_type"] == "standard"


def test_postgres_rds_spiky_burstable(knowledge):
    """Spiky traffic on RDS → burstable instance (no Serverless v2)."""
    result = recommend_database_target(
        engine="postgres", availability="multi-az", size_class="micro",
        io_workload="low", traffic="spiky", knowledge=knowledge,
    )
    assert result["aws_service"] == "RDS PostgreSQL"
    assert result["aws_config"]["instance_class"] == "db.t4g.micro"
    assert "min_acu" not in result["aws_config"] or result["aws_config"].get("min_acu") is None


# --- MySQL ---

def test_mysql_single_az(knowledge):
    result = recommend_database_target(
        engine="mysql", availability="single-az", size_class="small",
        io_workload="low", traffic="steady", knowledge=knowledge,
    )
    assert result["aws_service"] == "RDS MySQL"
    assert result["aws_config"]["instance_class"] == "db.t4g.small"


def test_mysql_aurora_multi_region(knowledge):
    result = recommend_database_target(
        engine="mysql", availability="multi-region", size_class="large",
        io_workload="medium", traffic="steady", knowledge=knowledge,
    )
    assert result["aws_service"] == "Aurora MySQL"
    assert result["aws_config"]["topology"] == "global-database"


# --- SQL Server ---

def test_sqlserver_rds(knowledge):
    """SQL Server: only RDS, no Graviton (t3 not t4g)."""
    result = recommend_database_target(
        engine="sqlserver", availability="single-az", size_class="micro",
        io_workload="low", traffic="steady", knowledge=knowledge,
    )
    assert result["aws_service"] == "RDS SQL Server"
    assert result["aws_config"]["instance_class"] == "db.t3.micro"


def test_sqlserver_aurora_fails(knowledge):
    """SQL Server + Aurora family → error (Aurora doesn't support SQL Server)."""
    result = recommend_database_target(
        engine="sqlserver", availability="multi-az-ha", size_class="medium",
        io_workload="low", traffic="steady", knowledge=knowledge,
    )
    assert "error" in result
    assert "does not support" in result["error"]


# --- Clarification / error cases ---

def test_availability_none_returns_clarification(knowledge):
    """Null availability → needs_clarification (never infers Aurora)."""
    result = recommend_database_target(
        engine="postgres", availability=None, size_class="micro",
        io_workload="low", traffic="steady", knowledge=knowledge,
    )
    assert result["needs_clarification"] == "availability"


def test_unknown_engine_returns_error(knowledge):
    result = recommend_database_target(
        engine="unknown_db", availability="single-az", size_class="micro",
        io_workload="low", traffic="steady", knowledge=knowledge,
    )
    assert "error" in result


def test_oracle_needs_confirmation(knowledge):
    """Oracle → needs_user_confirmation (escape path to Aurora Postgres)."""
    result = recommend_database_target(
        engine="oracle", availability="single-az", size_class="medium",
        io_workload="low", traffic="steady", knowledge=knowledge,
    )
    assert result["needs_clarification"] == "engine_choice"
    assert result["escape_path"]["target_engine"] == "postgres"


def test_mariadb_needs_confirmation(knowledge):
    """MariaDB → needs_user_confirmation (may prefer MySQL)."""
    result = recommend_database_target(
        engine="mariadb", availability="single-az", size_class="micro",
        io_workload="low", traffic="steady", knowledge=knowledge,
    )
    assert result["needs_clarification"] == "engine_choice"


# --- Migration tooling ---

def test_migration_tool_small_db(knowledge):
    result = recommend_database_target(
        engine="postgres", availability="single-az", size_class="micro",
        io_workload="low", traffic="steady", data_size_gb=5, knowledge=knowledge,
    )
    assert result["migration_tool"] == "pg_dump"


def test_migration_tool_medium_db(knowledge):
    result = recommend_database_target(
        engine="postgres", availability="single-az", size_class="medium",
        io_workload="low", traffic="steady", data_size_gb=50, knowledge=knowledge,
    )
    assert result["migration_tool"] == "pgcopydb"


def test_migration_tool_large_db(knowledge):
    result = recommend_database_target(
        engine="postgres", availability="multi-az", size_class="large",
        io_workload="high", traffic="steady", data_size_gb=600, knowledge=knowledge,
    )
    assert result["migration_tool"] == "AWS DMS"


def test_migration_tool_mysql_medium(knowledge):
    """MySQL uses mydumper instead of pgcopydb."""
    result = recommend_database_target(
        engine="mysql", availability="single-az", size_class="small",
        io_workload="low", traffic="steady", data_size_gb=50, knowledge=knowledge,
    )
    assert result["migration_tool"] == "mydumper"
