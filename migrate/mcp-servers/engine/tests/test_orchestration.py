"""Tests for orchestration tools."""

import json
from pathlib import Path

import pytest

from engine.knowledge import load_knowledge
from engine.tools.orchestration import (
    migration_status,
    migration_init,
    phase_router,
    phase_advance,
    phase_reset,
)

KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "knowledge"


@pytest.fixture
def knowledge():
    return load_knowledge(KNOWLEDGE_DIR)


@pytest.fixture
def routes_config(knowledge):
    return knowledge["heroku-to-aws/routes"]


def _write_status(tmp_path, phase, phases_override=None):
    """Helper to create a migration run with status."""
    run_dir = tmp_path / ".migration" / "0625-1400"
    run_dir.mkdir(parents=True, exist_ok=True)
    phases = phases_override or {
        "discover": "completed" if phase != "discover" else "in_progress",
        "clarify": "completed" if phase in ("design", "estimate", "generate", "feedback") else ("in_progress" if phase == "clarify" else "pending"),
        "design": "completed" if phase in ("estimate", "generate", "feedback") else ("in_progress" if phase == "design" else "pending"),
        "estimate": "completed" if phase in ("generate", "feedback") else ("in_progress" if phase == "estimate" else "pending"),
        "generate": "completed" if phase == "feedback" else ("in_progress" if phase == "generate" else "pending"),
        "feedback": "in_progress" if phase == "feedback" else "pending",
    }
    status = {"migration_id": "0625-1400", "skill": "heroku-to-aws", "current_phase": phase, "phases": phases}
    (run_dir / ".phase-status.json").write_text(json.dumps(status))
    return run_dir


class TestMigrationStatus:
    def test_no_migration_dir(self, tmp_path):
        result = migration_status(str(tmp_path))
        assert result["runs"] == []

    def test_finds_runs(self, tmp_path):
        _write_status(tmp_path, "discover")
        result = migration_status(str(tmp_path))
        assert len(result["runs"]) == 1
        assert result["runs"][0]["id"] == "0625-1400"


class TestMigrationInit:
    def test_creates_run(self, tmp_path):
        result = migration_init(str(tmp_path))
        assert result["status"] == "ok"
        assert (Path(result["path"]) / ".phase-status.json").exists()

    def test_creates_gitignore(self, tmp_path):
        migration_init(str(tmp_path))
        assert (tmp_path / ".migration" / ".gitignore").exists()

    def test_initial_phase_is_discover(self, tmp_path):
        result = migration_init(str(tmp_path))
        status = json.loads((Path(result["path"]) / ".phase-status.json").read_text())
        assert status["current_phase"] == "discover"
        assert status["phases"]["discover"] == "in_progress"


class TestPhaseRouter:
    def test_discover_with_terraform(self, tmp_path, routes_config):
        run_dir = _write_status(tmp_path, "discover")
        (tmp_path / "main.tf").touch()

        result = phase_router(str(run_dir), str(tmp_path), routes_config)
        route_ids = [r["id"] for r in result["routes"]]
        assert "terraform" in route_ids

    def test_discover_with_billing(self, tmp_path, routes_config):
        run_dir = _write_status(tmp_path, "discover")
        (tmp_path / "heroku-billing.csv").touch()

        result = phase_router(str(run_dir), str(tmp_path), routes_config)
        route_ids = [r["id"] for r in result["routes"]]
        assert "billing" in route_ids

    def test_discover_both(self, tmp_path, routes_config):
        run_dir = _write_status(tmp_path, "discover")
        (tmp_path / "main.tf").touch()
        (tmp_path / "billing-export.csv").touch()

        result = phase_router(str(run_dir), str(tmp_path), routes_config)
        route_ids = [r["id"] for r in result["routes"]]
        assert "terraform" in route_ids
        assert "billing" in route_ids

    def test_discover_no_files(self, tmp_path, routes_config):
        run_dir = _write_status(tmp_path, "discover")

        result = phase_router(str(run_dir), str(tmp_path), routes_config)
        route_ids = [r["id"] for r in result["routes"]]
        # Only assemble (always) fires — terraform and billing skipped
        assert "terraform" not in route_ids
        assert "billing" not in route_ids
        assert "assemble" in route_ids

    def test_clarify_requires_discover_completed(self, tmp_path, routes_config):
        run_dir = _write_status(tmp_path, "clarify")

        result = phase_router(str(run_dir), str(tmp_path), routes_config)
        assert result["current_phase"] == "clarify"
        route_ids = [r["id"] for r in result["routes"]]
        assert "clarify" in route_ids

    def test_design_requires_clarify(self, tmp_path, routes_config):
        run_dir = _write_status(tmp_path, "design")
        (run_dir / "heroku-resource-inventory.json").write_text("{}")

        result = phase_router(str(run_dir), str(tmp_path), routes_config)
        route_ids = [r["id"] for r in result["routes"]]
        assert "design" in route_ids

    def test_design_skipped_without_inventory(self, tmp_path, routes_config):
        run_dir = _write_status(tmp_path, "design")

        result = phase_router(str(run_dir), str(tmp_path), routes_config)
        assert result["routes"] == []


class TestPhaseAdvance:
    def test_advance_discover_to_clarify(self, tmp_path, routes_config):
        run_dir = _write_status(tmp_path, "discover")
        (tmp_path / "main.tf").touch()
        (run_dir / "_terraform-discovery.json").write_text("{}")
        (run_dir / "heroku-resource-inventory.json").write_text("{}")

        result = phase_advance(str(run_dir), str(tmp_path), routes_config)
        assert result["status"] == "advanced"
        assert result["from"] == "discover"
        assert result["to"] == "clarify"

    def test_gate_fails_without_artifacts(self, tmp_path, routes_config):
        run_dir = _write_status(tmp_path, "discover")
        (tmp_path / "main.tf").touch()
        # heroku-resource-inventory.json NOT created

        result = phase_advance(str(run_dir), str(tmp_path), routes_config)
        assert result["status"] == "gate_failed"
        assert len(result["missing_artifacts"]) > 0


class TestPhaseReset:
    def test_reset_to_discover(self, tmp_path, routes_config):
        run_dir = _write_status(tmp_path, "design")

        result = phase_reset(str(run_dir), "discover", routes_config)
        assert result["status"] == "reset"
        assert result["current_phase"] == "discover"

        status = json.loads((run_dir / ".phase-status.json").read_text())
        assert status["phases"]["discover"] == "in_progress"
        assert status["phases"]["clarify"] == "pending"
        assert status["phases"]["design"] == "pending"

    def test_reset_unknown_phase(self, tmp_path, routes_config):
        run_dir = _write_status(tmp_path, "discover")

        result = phase_reset(str(run_dir), "nonexistent", routes_config)
        assert "error" in result
