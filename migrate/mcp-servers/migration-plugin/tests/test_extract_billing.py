"""Tests for extract_billing_summary tool."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from migration_orchestrator.tools.extract_billing import extract_billing_summary


@pytest.fixture
def billing_csv(tmp_path):
    """Create a sample GCP billing export CSV."""
    csv_content = """service_description,sku_description,cost,region,resourceGlobalName
Cloud Run,Cloud Run - CPU Allocation Time,300.00,us-central1,
Cloud Run,Cloud Run - Memory Allocation Time,150.00,us-central1,
Cloud SQL,Cloud SQL for PostgreSQL - DB custom CORE,500.00,us-central1,
Cloud SQL,Cloud SQL for PostgreSQL - DB custom RAM,300.00,us-central1,
Vertex AI,Vertex AI Prediction - Online Prediction,400.00,us-central1,
Vertex AI,Generative AI - Gemini Pro Input Tokens,200.00,us-central1,
Compute Engine,Commitment v1: E2 Cpu in Americas for 1 Year,75.00,us-central1,project_commitments/123
Compute Engine,Commitment v1: E2 Ram in Americas for 1 Year,75.00,us-central1,project_commitments/456
"""
    billing_file = tmp_path / "gcp-billing-export.csv"
    billing_file.write_text(csv_content)
    return tmp_path


@pytest.fixture
def billing_json(tmp_path):
    """Create a sample BigQuery billing export JSON."""
    data = [
        {"service_description": "Cloud Storage", "sku_description": "Standard Storage US", "cost": "120.00", "region": "us"},
        {"service_description": "Cloud Functions", "sku_description": "Invocations", "cost": "45.00", "region": "us-central1"},
        {"service_description": "Cloud Functions", "sku_description": "CPU Time", "cost": "80.00", "region": "us-central1"},
    ]
    billing_file = tmp_path / "cost-report.json"
    billing_file.write_text(json.dumps(data))
    return tmp_path


@pytest.fixture
def billing_with_discounts(tmp_path):
    """CSV with discount columns."""
    csv_content = """service_description,sku_description,cost,committedUsageDiscount,sustainedUsageDiscount,region
Cloud Run,CPU Allocation Time,300.00,-30.00,0,us-central1
Cloud SQL,DB custom CORE,500.00,-50.00,-25.00,us-central1
"""
    billing_file = tmp_path / "billing-export.csv"
    billing_file.write_text(csv_content)
    return tmp_path


class TestFindBillingFile:
    def test_no_billing_files(self, tmp_path):
        result = extract_billing_summary(str(tmp_path))
        assert result["status"] == "skipped"
        assert "No billing files found" in result["reason"]

    def test_finds_csv(self, billing_csv):
        result = extract_billing_summary(str(billing_csv))
        assert result["status"] == "ok"

    def test_finds_json(self, billing_json):
        result = extract_billing_summary(str(billing_json))
        assert result["status"] == "ok"

    def test_finds_nested(self, tmp_path):
        nested = tmp_path / "data" / "exports"
        nested.mkdir(parents=True)
        (nested / "usage-report.csv").write_text(
            "service_description,sku_description,cost\nCloud Run,CPU,100.00\n"
        )
        result = extract_billing_summary(str(tmp_path))
        assert result["status"] == "ok"


class TestServiceAggregation:
    def test_aggregates_services(self, billing_csv):
        result = extract_billing_summary(str(billing_csv))
        profile = result["profile"]
        services = {s["gcp_service"]: s for s in profile["services"]}
        assert "Cloud Run" in services
        assert services["Cloud Run"]["monthly_cost"] == 450.00
        assert "Cloud SQL" in services
        assert services["Cloud SQL"]["monthly_cost"] == 800.00

    def test_excludes_commitment_fees_from_services(self, billing_csv):
        result = extract_billing_summary(str(billing_csv))
        profile = result["profile"]
        # Commitment fee rows should not inflate Compute Engine service cost
        services = {s["gcp_service"]: s for s in profile["services"]}
        assert "Compute Engine" not in services  # Only commitment rows, no actual usage

    def test_percentage_of_total(self, billing_csv):
        result = extract_billing_summary(str(billing_csv))
        profile = result["profile"]
        total_pct = sum(s["percentage_of_total"] for s in profile["services"])
        assert 0.99 <= total_pct <= 1.01

    def test_top_skus(self, billing_csv):
        result = extract_billing_summary(str(billing_csv))
        profile = result["profile"]
        services = {s["gcp_service"]: s for s in profile["services"]}
        cloud_sql = services["Cloud SQL"]
        assert len(cloud_sql["top_skus"]) == 2
        assert cloud_sql["top_skus"][0]["monthly_cost"] == 500.00

    def test_terraform_type_mapping(self, billing_csv):
        result = extract_billing_summary(str(billing_csv))
        profile = result["profile"]
        services = {s["gcp_service"]: s for s in profile["services"]}
        assert services["Cloud Run"]["gcp_service_type"] == "google_cloud_run_service"
        assert services["Cloud SQL"]["gcp_service_type"] == "google_sql_database_instance"


class TestCommitments:
    def test_detects_cuds(self, billing_csv):
        result = extract_billing_summary(str(billing_csv))
        profile = result["profile"]
        assert profile["commitments"]["has_active_cuds"] is True
        assert profile["commitments"]["total_monthly_commitment_fees"] == 150.00
        assert len(profile["commitments"]["details"]) == 2

    def test_cud_details(self, billing_csv):
        result = extract_billing_summary(str(billing_csv))
        details = result["profile"]["commitments"]["details"]
        assert details[0]["type"] == "resource_based"
        assert details[0]["term"] == "1_year"
        assert details[0]["monthly_fee"] == 75.00

    def test_no_cuds(self, billing_json):
        result = extract_billing_summary(str(billing_json))
        profile = result["profile"]
        assert profile["commitments"]["has_active_cuds"] is False
        assert profile["commitments"]["total_monthly_commitment_fees"] == 0.0

    def test_discount_credits(self, billing_with_discounts):
        result = extract_billing_summary(str(billing_with_discounts))
        profile = result["profile"]
        assert profile["commitments"]["has_active_cuds"] is True
        assert profile["cost_basis"]["discount_breakdown"]["committed_usage_discount"] == -80.00
        assert profile["cost_basis"]["discount_breakdown"]["sustained_usage_discount"] == -25.00


class TestAISignals:
    def test_detects_vertex_ai(self, billing_csv):
        result = extract_billing_summary(str(billing_csv))
        assert result["ai_signals_detected"] is True
        profile = result["profile"]
        assert profile["ai_signals"]["detected"] is True
        assert "Vertex AI" in profile["ai_signals"]["services"]

    def test_no_ai_signals(self, billing_json):
        result = extract_billing_summary(str(billing_json))
        assert result["ai_signals_detected"] is False
        profile = result["profile"]
        assert profile["ai_signals"]["detected"] is False

    def test_ai_signals_on_service(self, billing_csv):
        result = extract_billing_summary(str(billing_csv))
        profile = result["profile"]
        services = {s["gcp_service"]: s for s in profile["services"]}
        assert "vertex_ai" in services["Vertex AI"]["ai_signals"]
        assert "generative_ai" in services["Vertex AI"]["ai_signals"]
        assert services["Cloud Run"]["ai_signals"] == []


class TestOutputFile:
    def test_writes_billing_profile(self, billing_csv):
        output_dir = billing_csv / "migration-output"
        result = extract_billing_summary(str(billing_csv), output_dir=str(output_dir))
        assert result["status"] == "ok"
        out_file = output_dir / "billing-profile.json"
        assert out_file.exists()
        data = json.loads(out_file.read_text())
        assert data["summary"]["total_monthly_spend"] > 0

    def test_no_write_without_output_dir(self, billing_csv):
        result = extract_billing_summary(str(billing_csv))
        assert result["status"] == "ok"
        # No file written anywhere in the project dir
        assert not (billing_csv / "billing-profile.json").exists()


class TestSummary:
    def test_total_spend(self, billing_csv):
        result = extract_billing_summary(str(billing_csv))
        profile = result["profile"]
        # 450 (Cloud Run) + 800 (Cloud SQL) + 600 (Vertex AI) = 1850
        assert profile["summary"]["total_monthly_spend"] == 1850.00

    def test_service_count(self, billing_csv):
        result = extract_billing_summary(str(billing_csv))
        profile = result["profile"]
        assert profile["summary"]["service_count"] == 3

    def test_metadata(self, billing_csv):
        result = extract_billing_summary(str(billing_csv))
        profile = result["profile"]
        assert profile["metadata"]["billing_source"] == "gcp-billing-export.csv"
        assert profile["metadata"]["project_directory"] == str(billing_csv)
