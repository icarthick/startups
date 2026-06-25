"""Tests for scan_heroku_terraform tool."""

import json
from pathlib import Path

import pytest

from orchestrator.tools.scan_heroku_terraform import scan_heroku_terraform


@pytest.fixture
def heroku_project(tmp_path):
    """Project with Heroku Terraform + Procfile."""
    (tmp_path / "heroku.tf").write_text('''
resource "heroku_app" "web" {
  name   = "my-web-app"
  region = "us"
  stack  = "heroku-22"
}

resource "heroku_addon" "postgres" {
  app_id = heroku_app.web.id
  plan   = "heroku-postgresql:standard-0"
}

resource "heroku_formation" "web" {
  app_id   = heroku_app.web.id
  type     = "web"
  quantity = 2
  size     = "standard-2x"
}

resource "heroku_domain" "www" {
  app_id   = heroku_app.web.id
  hostname = "www.example.com"
}
''')
    (tmp_path / "Procfile").write_text("web: gunicorn app:app\nworker: celery -A tasks worker\n")
    return tmp_path


class TestNoFiles:
    def test_empty_dir(self, tmp_path):
        result = scan_heroku_terraform(str(tmp_path))
        assert result["status"] == "skipped"

    def test_no_heroku_resources(self, tmp_path):
        (tmp_path / "main.tf").write_text('resource "aws_instance" "web" { ami = "abc" }')
        result = scan_heroku_terraform(str(tmp_path))
        assert result["status"] == "skipped"


class TestResourceExtraction:
    def test_extracts_app(self, heroku_project):
        result = scan_heroku_terraform(str(heroku_project))
        assert result["status"] == "ok"
        assert result["summary"]["total_apps"] == 1

    def test_extracts_all_resources(self, heroku_project):
        result = scan_heroku_terraform(str(heroku_project))
        assert result["summary"]["total_resources"] >= 4  # app + addon + formation + domain + worker from procfile

    def test_resolves_app_reference(self, heroku_project):
        mdir = heroku_project / ".migration" / "test"
        mdir.mkdir(parents=True)
        scan_heroku_terraform(str(heroku_project), str(mdir))
        data = json.loads((mdir / "_terraform-discovery.json").read_text())
        addon = next(r for r in data["resources"] if r["resource_type"] == "addon")
        assert addon["heroku_app"] == "my-web-app"

    def test_addon_plan_parsing(self, heroku_project):
        mdir = heroku_project / ".migration" / "test"
        mdir.mkdir(parents=True)
        scan_heroku_terraform(str(heroku_project), str(mdir))
        data = json.loads((mdir / "_terraform-discovery.json").read_text())
        addon = next(r for r in data["resources"] if r["resource_type"] == "addon")
        assert addon["config"]["addon_service"] == "heroku-postgresql"
        assert addon["config"]["plan"] == "standard-0"


class TestProcfileIntegration:
    def test_populates_command(self, heroku_project):
        mdir = heroku_project / ".migration" / "test"
        mdir.mkdir(parents=True)
        scan_heroku_terraform(str(heroku_project), str(mdir))
        data = json.loads((mdir / "_terraform-discovery.json").read_text())
        web_formation = next(r for r in data["resources"] if r["resource_type"] == "formation" and r["config"]["process_type"] == "web")
        assert web_formation["config"]["command"] == "gunicorn app:app"

    def test_adds_procfile_only_process(self, heroku_project):
        mdir = heroku_project / ".migration" / "test"
        mdir.mkdir(parents=True)
        scan_heroku_terraform(str(heroku_project), str(mdir))
        data = json.loads((mdir / "_terraform-discovery.json").read_text())
        worker = next(r for r in data["resources"] if r["resource_type"] == "formation" and r["config"]["process_type"] == "worker")
        assert worker["config"]["command"] == "celery -A tasks worker"
        assert worker["config"]["quantity"] == 0
        assert worker["source"] == "procfile"


class TestCedarFirDetection:
    def test_cedar_detection(self, heroku_project):
        mdir = heroku_project / ".migration" / "test"
        mdir.mkdir(parents=True)
        scan_heroku_terraform(str(heroku_project), str(mdir))
        data = json.loads((mdir / "_terraform-discovery.json").read_text())
        assert data["apps"][0]["heroku_generation"] == "cedar"

    def test_fir_detection(self, tmp_path):
        (tmp_path / "app.tf").write_text('resource "heroku_app" "api" {\n  name = "api"\n  region = "us"\n  stack = "fir"\n}\n')
        mdir = tmp_path / ".migration" / "test"
        mdir.mkdir(parents=True)
        scan_heroku_terraform(str(tmp_path), str(mdir))
        data = json.loads((mdir / "_terraform-discovery.json").read_text())
        assert data["apps"][0]["heroku_generation"] == "fir"


class TestOutputFile:
    def test_writes_file(self, heroku_project):
        mdir = heroku_project / ".migration" / "test"
        mdir.mkdir(parents=True)
        scan_heroku_terraform(str(heroku_project), str(mdir))
        assert (mdir / "_terraform-discovery.json").exists()

    def test_no_write_without_migration_dir(self, heroku_project):
        result = scan_heroku_terraform(str(heroku_project))
        assert result["status"] == "ok"
        # No file written
        assert not (heroku_project / "_terraform-discovery.json").exists()


class TestMetadata:
    def test_discovery_sources(self, heroku_project):
        mdir = heroku_project / ".migration" / "test"
        mdir.mkdir(parents=True)
        scan_heroku_terraform(str(heroku_project), str(mdir))
        data = json.loads((mdir / "_terraform-discovery.json").read_text())
        assert "terraform" in data["metadata"]["discovery_sources"]
        assert "procfile" in data["metadata"]["discovery_sources"]

    def test_tf_metadata(self, heroku_project):
        mdir = heroku_project / ".migration" / "test"
        mdir.mkdir(parents=True)
        scan_heroku_terraform(str(heroku_project), str(mdir))
        data = json.loads((mdir / "_terraform-discovery.json").read_text())
        assert data["terraform_metadata"]["found"] is True
        assert data["terraform_metadata"]["tf_files_scanned"] == 1
