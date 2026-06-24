"""Unit tests for validate_design."""

from pathlib import Path

import pytest

from migration_tools.knowledge import load_knowledge
from migration_tools.tools.validate_design import validate_design

KNOWLEDGE_DIR = Path(__file__).resolve().parents[1].parent / "knowledge"


@pytest.fixture(scope="module")
def knowledge():
    return load_knowledge(KNOWLEDGE_DIR)


def _valid_design():
    """Minimal valid aws-design.json."""
    return {
        "clusters": [{
            "cluster_id": "db_sql_us-central1_001",
            "gcp_region": "us-central1",
            "aws_region": "us-east-1",
            "resources": [{
                "gcp_address": "google_sql_database_instance.main",
                "gcp_type": "google_sql_database_instance",
                "gcp_config": {"database_version": "POSTGRES_15"},
                "aws_service": "RDS PostgreSQL",
                "aws_config": {"instance_class": "db.t4g.micro", "multi_az": False},
                "confidence": "inferred",
                "human_expertise_required": False,
                "rationale": "Q6 single-az → RDS",
                "rubric_applied": ["availability=single-az → RDS"],
            }],
        }],
        "warnings": [],
    }


def test_valid_design_passes(knowledge):
    result = validate_design(_valid_design(), knowledge=knowledge)
    assert result["valid"] is True
    assert result["checks_passed"] == result["checks_total"]
    assert result["violations"] == []


def test_empty_clusters_fails(knowledge):
    design = {"clusters": [], "warnings": []}
    result = validate_design(design, knowledge=knowledge)
    assert result["valid"] is False
    assert any("empty" in v for v in result["violations"])


def test_missing_aws_service_fails(knowledge):
    design = _valid_design()
    del design["clusters"][0]["resources"][0]["aws_service"]
    result = validate_design(design, knowledge=knowledge)
    assert result["valid"] is False
    assert any("aws_service" in v for v in result["violations"])


def test_missing_human_expertise_fails(knowledge):
    design = _valid_design()
    del design["clusters"][0]["resources"][0]["human_expertise_required"]
    result = validate_design(design, knowledge=knowledge)
    assert result["valid"] is False
    assert any("human_expertise_required" in v for v in result["violations"])


def test_invalid_confidence_fails(knowledge):
    design = _valid_design()
    design["clusters"][0]["resources"][0]["confidence"] = "guessed"
    result = validate_design(design, knowledge=knowledge)
    assert result["valid"] is False
    assert any("confidence" in v for v in result["violations"])


def test_bigquery_not_deferred_fails(knowledge):
    design = _valid_design()
    design["clusters"][0]["resources"][0]["gcp_type"] = "google_bigquery_dataset"
    design["clusters"][0]["resources"][0]["aws_service"] = "Athena"
    result = validate_design(design, knowledge=knowledge)
    assert result["valid"] is False
    assert any("Deferred" in v for v in result["violations"])


def test_bigquery_deferred_passes(knowledge):
    design = _valid_design()
    r = design["clusters"][0]["resources"][0]
    r["gcp_type"] = "google_bigquery_dataset"
    r["gcp_address"] = "google_bigquery_dataset.analytics"
    r["aws_service"] = "Deferred — specialist engagement"
    r["human_expertise_required"] = True
    result = validate_design(design, knowledge=knowledge)
    assert result["valid"] is True


def test_duplicate_address_fails(knowledge):
    design = _valid_design()
    # Add a second resource with same address
    design["clusters"][0]["resources"].append(design["clusters"][0]["resources"][0].copy())
    result = validate_design(design, knowledge=knowledge)
    assert result["valid"] is False
    assert any("Duplicate" in v for v in result["violations"])


def test_empty_rationale_fails(knowledge):
    design = _valid_design()
    design["clusters"][0]["resources"][0]["rationale"] = ""
    result = validate_design(design, knowledge=knowledge)
    assert result["valid"] is False
    assert any("rationale" in v for v in result["violations"])


def test_sql_invalid_service_fails(knowledge):
    design = _valid_design()
    design["clusters"][0]["resources"][0]["aws_service"] = "Aurora DSQL"
    result = validate_design(design, knowledge=knowledge)
    assert result["valid"] is False
    assert any("not in valid set" in v for v in result["violations"])
