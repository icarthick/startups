"""Tests for scan_tf_references tool."""

import os
import tempfile
from pathlib import Path

from migration_orchestrator.tools.scan_tf_references import scan_tf_references


def _write_tf(tmp_dir, filename, content):
    path = Path(tmp_dir) / filename
    path.write_text(content)
    return path


def test_basic_reference_extraction():
    with tempfile.TemporaryDirectory() as td:
        _write_tf(td, "main.tf", '''
resource "google_compute_network" "vpc" {
  name = "my-vpc"
}

resource "google_compute_subnetwork" "subnet" {
  name    = "my-subnet"
  network = google_compute_network.vpc.id
}
''')
        result = scan_tf_references(td)
        edges = result["edges"]
        assert len(edges) == 1
        assert edges[0]["from"] == "google_compute_subnetwork.subnet"
        assert edges[0]["to"] == "google_compute_network.vpc"


def test_interpolation_references():
    with tempfile.TemporaryDirectory() as td:
        _write_tf(td, "iam.tf", '''
resource "google_service_account" "payment" {
  account_id = "payment-sa"
}

resource "google_project_iam_member" "binding" {
  member = "serviceAccount:${google_service_account.payment.email}"
}
''')
        result = scan_tf_references(td)
        edges = result["edges"]
        assert len(edges) == 1
        assert edges[0]["to"] == "google_service_account.payment"
        assert edges[0]["file"] == "iam.tf"


def test_file_map_correctness():
    with tempfile.TemporaryDirectory() as td:
        _write_tf(td, "networking.tf", '''
resource "google_compute_network" "vpc" {
  name = "vpc"
}
''')
        _write_tf(td, "compute.tf", '''
resource "google_compute_instance" "vm" {
  name = "vm"
}
''')
        result = scan_tf_references(td)
        assert result["file_map"]["google_compute_network.vpc"] == "networking.tf"
        assert result["file_map"]["google_compute_instance.vm"] == "compute.tf"


def test_comments_are_ignored():
    with tempfile.TemporaryDirectory() as td:
        _write_tf(td, "main.tf", '''
resource "google_compute_network" "vpc" {
  name = "vpc"
}

resource "google_compute_subnetwork" "subnet" {
  # network = google_compute_network.vpc.id
  // network = google_compute_network.vpc.id
  /* network = google_compute_network.vpc.id */
  name = "subnet"
}
''')
        result = scan_tf_references(td)
        assert len(result["edges"]) == 0


def test_unresolved_variables():
    with tempfile.TemporaryDirectory() as td:
        _write_tf(td, "networking.tf", '''
resource "google_compute_network" "vpc" {
  name = var.network_name
  cidr = local.cidr_block
  mod  = module.network.output
}
''')
        result = scan_tf_references(td)
        unrefs = result["unresolved_references"]
        refs = {u["reference"] for u in unrefs}
        assert "var.network_name" in refs
        assert "local.cidr_block" in refs
        assert "module.network.output" in refs


def test_for_each_detection():
    with tempfile.TemporaryDirectory() as td:
        _write_tf(td, "iam.tf", '''
resource "google_project_iam_member" "members" {
  for_each = toset(["roles/viewer", "roles/editor"])
  role     = each.value
}
''')
        result = scan_tf_references(td)
        fe = result["for_each_resources"]
        assert len(fe) == 1
        assert fe[0]["address"] == "google_project_iam_member.members"
        assert "toset" in fe[0]["iterator_expr"]
        # Also check resources_found
        r = result["resources_found"][0]
        assert r["has_for_each"] is True
        assert r["has_count"] is False


def test_no_self_references():
    with tempfile.TemporaryDirectory() as td:
        _write_tf(td, "main.tf", '''
resource "google_compute_instance" "vm" {
  name = google_compute_instance.vm.name
}
''')
        result = scan_tf_references(td)
        assert len(result["edges"]) == 0


def test_summary_counts():
    with tempfile.TemporaryDirectory() as td:
        _write_tf(td, "main.tf", '''
resource "google_compute_network" "vpc" {
  name = "vpc"
}

resource "google_compute_subnetwork" "subnet" {
  network = google_compute_network.vpc.id
}
''')
        result = scan_tf_references(td)
        s = result["summary"]
        assert s["files_scanned"] == 1
        assert s["resources_found"] == 2
        assert s["edges_found"] == 1
        assert s["unresolved"] == 0


def test_empty_directory():
    with tempfile.TemporaryDirectory() as td:
        result = scan_tf_references(td)
        assert result["resources_found"] == []
        assert result["edges"] == []
        assert result["file_map"] == {}
        assert result["unresolved_references"] == []
        assert result["for_each_resources"] == []
        assert result["summary"]["files_scanned"] == 0
