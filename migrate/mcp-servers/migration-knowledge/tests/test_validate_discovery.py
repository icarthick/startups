"""Unit tests for validate_discovery."""

import pytest

from migration_knowledge.tools.validate_discovery import validate_discovery


# --- IaC validation ---

def test_iac_valid():
    """Valid inventory + clusters → passes."""
    content = {
        "inventory": {
            "metadata": {"report_date": "2026-06-25"},
            "summary": {"total_resources": 2, "primary_resources": 1, "total_clusters": 1},
            "resources": [
                {"address": "google_compute_network.vpc", "type": "google_compute_network", "name": "vpc", "classification": "PRIMARY", "tier": "networking", "confidence": 0.99, "config": {}, "depth": 0, "cluster_id": "net-001"},
                {"address": "google_compute_firewall.fw", "type": "google_compute_firewall", "name": "fw", "classification": "SECONDARY", "tier": "networking", "confidence": 0.99, "config": {}, "depth": 1, "cluster_id": "net-001"},
            ],
            "ai_detection": {"has_ai_workload": False},
        },
        "clusters": {
            "clusters": [
                {"cluster_id": "net-001", "gcp_region": "us-central1", "primary_resources": ["google_compute_network.vpc"], "secondary_resources": ["google_compute_firewall.fw"], "creation_order_depth": 0},
            ]
        },
    }
    result = validate_discovery(artifact_type="iac", content=content)
    assert result["valid"] is True


def test_iac_missing_resource_fields():
    """Resource missing required fields → violations."""
    content = {
        "inventory": {
            "metadata": {},
            "summary": {"total_resources": 1, "primary_resources": 1, "total_clusters": 1},
            "resources": [{"address": "google_x.y", "type": "google_x"}],  # missing most fields
        },
        "clusters": {"clusters": [{"cluster_id": "c1", "gcp_region": "us-c1", "primary_resources": [], "secondary_resources": [], "creation_order_depth": 0}]},
    }
    result = validate_discovery(artifact_type="iac", content=content)
    assert result["valid"] is False
    assert any("missing" in v for v in result["violations"])


def test_iac_cluster_id_mismatch():
    """Inventory references cluster_id not in clusters file → violation."""
    content = {
        "inventory": {
            "metadata": {},
            "summary": {"total_resources": 1, "primary_resources": 1, "total_clusters": 1},
            "resources": [{"address": "a.b", "type": "a", "name": "b", "classification": "PRIMARY", "tier": "compute", "confidence": 0.9, "config": {}, "depth": 0, "cluster_id": "orphan-cluster"}],
        },
        "clusters": {"clusters": [{"cluster_id": "different-cluster", "gcp_region": "us-c1", "primary_resources": [], "secondary_resources": [], "creation_order_depth": 0}]},
    }
    result = validate_discovery(artifact_type="iac", content=content)
    assert result["valid"] is False
    assert any("orphan-cluster" in v for v in result["violations"])


def test_iac_invalid_classification():
    """Invalid classification value → violation."""
    content = {
        "inventory": {
            "metadata": {},
            "summary": {"total_resources": 1, "primary_resources": 1, "total_clusters": 1},
            "resources": [{"address": "a.b", "type": "a", "name": "b", "classification": "UNKNOWN", "tier": "compute", "confidence": 0.9, "config": {}, "depth": 0, "cluster_id": "c1"}],
        },
        "clusters": {"clusters": [{"cluster_id": "c1", "gcp_region": "us-c1", "primary_resources": [], "secondary_resources": [], "creation_order_depth": 0}]},
    }
    result = validate_discovery(artifact_type="iac", content=content)
    assert result["valid"] is False
    assert any("classification" in v for v in result["violations"])


# --- AI profile validation ---

def test_ai_profile_valid():
    """Valid ai-workload-profile → passes."""
    content = {
        "metadata": {"profile_source": "app_code", "report_date": "2026-06-25"},
        "summary": {"ai_source": "openai", "overall_confidence": 85},
    }
    result = validate_discovery(artifact_type="ai-profile", content=content)
    assert result["valid"] is True


def test_ai_profile_missing_summary():
    """Missing summary → violation."""
    content = {"metadata": {"profile_source": "app_code"}}
    result = validate_discovery(artifact_type="ai-profile", content=content)
    assert result["valid"] is False


# --- Billing validation ---

def test_billing_valid():
    """Valid billing-profile → passes."""
    content = {
        "summary": {"total_monthly_spend": 1200.00},
        "services": [{"gcp_service": "Cloud Run", "monthly_cost": 450.00}],
    }
    result = validate_discovery(artifact_type="billing", content=content)
    assert result["valid"] is True


def test_billing_empty_services():
    """Empty services array → violation."""
    content = {"summary": {"total_monthly_spend": 0}, "services": []}
    result = validate_discovery(artifact_type="billing", content=content)
    assert result["valid"] is False


def test_billing_missing_cost():
    """Service missing monthly_cost → violation."""
    content = {"summary": {"total_monthly_spend": 100}, "services": [{"gcp_service": "X"}]}
    result = validate_discovery(artifact_type="billing", content=content)
    assert result["valid"] is False


# --- Edge cases ---

def test_unknown_artifact_type():
    """Unknown type → error."""
    result = validate_discovery(artifact_type="bogus", content={})
    assert result["valid"] is False
    assert any("Unknown" in v for v in result["violations"])
