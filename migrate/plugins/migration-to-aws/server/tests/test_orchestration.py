"""Unit tests for orchestration tools."""

import json
from pathlib import Path

import pytest

from migration_tools.tools.orchestration import migration_status, migration_init


# --- migration_status ---

def test_status_no_migration_dir(tmp_path):
    """No .migration/ directory → empty list."""
    result = migration_status(project_dir=str(tmp_path))
    assert result["migrations"] == []
    assert result["latest"] is None


def test_status_empty_migration_dir(tmp_path):
    """Empty .migration/ directory → empty list."""
    (tmp_path / ".migration").mkdir()
    result = migration_status(project_dir=str(tmp_path))
    assert result["migrations"] == []
    assert result["latest"] is None


def test_status_one_valid_run(tmp_path):
    """One run with valid status → returns it."""
    run_dir = tmp_path / ".migration" / "0624-1430"
    run_dir.mkdir(parents=True)
    status = {
        "migration_id": "0624-1430",
        "last_updated": "2026-06-24T14:30:00",
        "current_phase": "design",
        "phases": {
            "discover": "completed",
            "clarify": "completed",
            "design": "in_progress",
            "estimate": "pending",
            "generate": "pending",
            "feedback": "pending",
        },
    }
    (run_dir / ".phase-status.json").write_text(json.dumps(status))

    result = migration_status(project_dir=str(tmp_path))
    assert len(result["migrations"]) == 1
    assert result["latest"] == "0624-1430"
    assert result["migrations"][0]["current_phase"] == "design"


def test_status_multiple_runs(tmp_path):
    """Multiple runs → returns all, latest is last alphabetically."""
    for run_id in ["0624-1000", "0624-1430"]:
        run_dir = tmp_path / ".migration" / run_id
        run_dir.mkdir(parents=True)
        status = {"migration_id": run_id, "current_phase": "discover", "phases": {}}
        (run_dir / ".phase-status.json").write_text(json.dumps(status))

    result = migration_status(project_dir=str(tmp_path))
    assert len(result["migrations"]) == 2
    assert result["latest"] == "0624-1430"


def test_status_invalid_json(tmp_path):
    """Corrupted status file → reports error, doesn't crash."""
    run_dir = tmp_path / ".migration" / "0624-1430"
    run_dir.mkdir(parents=True)
    (run_dir / ".phase-status.json").write_text("not json{{{")

    result = migration_status(project_dir=str(tmp_path))
    assert len(result["migrations"]) == 1
    assert result["migrations"][0]["error"] == "Invalid JSON in .phase-status.json"


def test_status_missing_status_file(tmp_path):
    """Run dir exists but no status file → reports error."""
    (tmp_path / ".migration" / "0624-1430").mkdir(parents=True)

    result = migration_status(project_dir=str(tmp_path))
    assert len(result["migrations"]) == 1
    assert result["migrations"][0]["error"] == "Missing .phase-status.json"


def test_status_ignores_gitignore(tmp_path):
    """The .gitignore file in .migration/ is not listed as a run."""
    mig = tmp_path / ".migration"
    mig.mkdir()
    (mig / ".gitignore").write_text("*\n")

    result = migration_status(project_dir=str(tmp_path))
    assert result["migrations"] == []


# --- migration_init ---

def test_init_creates_structure(tmp_path):
    """Creates .migration/MMDD-HHMM/ with gitignore and status file."""
    result = migration_init(project_dir=str(tmp_path))

    assert result["status"] == "initialized"
    assert result["current_phase"] == "discover"

    migration_dir = tmp_path / ".migration" / result["migration_id"]
    assert migration_dir.exists()
    assert (tmp_path / ".migration" / ".gitignore").exists()
    assert (migration_dir / ".phase-status.json").exists()


def test_init_status_file_content(tmp_path):
    """Status file has correct initial state."""
    result = migration_init(project_dir=str(tmp_path))

    status_file = tmp_path / ".migration" / result["migration_id"] / ".phase-status.json"
    status = json.loads(status_file.read_text())

    assert status["current_phase"] == "discover"
    assert status["phases"]["discover"] == "in_progress"
    assert status["phases"]["clarify"] == "pending"
    assert status["phases"]["design"] == "pending"


def test_init_does_not_overwrite_gitignore(tmp_path):
    """If .gitignore already exists, don't overwrite it."""
    mig = tmp_path / ".migration"
    mig.mkdir()
    (mig / ".gitignore").write_text("custom content\n")

    migration_init(project_dir=str(tmp_path))
    assert (mig / ".gitignore").read_text() == "custom content\n"


def test_init_multiple_runs(tmp_path):
    """Can init multiple times (different timestamps in practice)."""
    result1 = migration_init(project_dir=str(tmp_path))
    # Second call would get same timestamp in tests (same second)
    # Just verify it doesn't crash
    result2 = migration_init(project_dir=str(tmp_path))
    assert result2["status"] == "initialized"
