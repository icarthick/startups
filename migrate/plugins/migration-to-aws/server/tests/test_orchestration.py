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


# --- phase_router ---

from migration_tools.tools.orchestration import phase_router


@pytest.fixture
def routes_config():
    """Minimal routes config for testing."""
    return {
        "skill": "test-skill",
        "phases": ["discover", "clarify", "design"],
        "routes": {
            "discover": {
                "routes": [
                    {"id": "iac", "trigger": {"glob": ["**/*.tf"]}, "file": "discover-iac.md", "produces": ["inventory.json"]},
                    {"id": "billing-full", "trigger": {"glob": ["**/*billing*.csv"]}, "do_not_run_with_routes": ["iac"], "file": "discover-billing.md", "produces": ["billing.json"]},
                    {"id": "billing-lightweight", "trigger": {"glob": ["**/*billing*.csv"]}, "run_only_with_routes": ["iac"], "file": "discover-billing-lightweight.md", "produces": ["billing.json"]},
                    {"id": "preview", "trigger": {"always": True}, "file": "discover-preview.md", "produces": []},
                ]
            },
            "clarify": {
                "requires_phase": "discover",
                "routes": [
                    {"id": "global", "trigger": {"artifact_exists": ["inventory.json"]}, "file": "clarify-global.md", "produces": ["preferences.json"]},
                    {"id": "ai-only", "trigger": {"artifact_exists": ["ai-profile.json"], "artifact_absent": ["inventory.json"]}, "file": "clarify-ai-only.md", "produces": ["preferences.json"]},
                ]
            },
            "design": {
                "requires_phase": "clarify",
                "routes": [
                    {"id": "infra", "trigger": {"artifact_exists": ["inventory.json"]}, "file": "design-infra.md", "produces": ["aws-design.json"]},
                ]
            },
        },
    }


def _write_status(tmp_path, phase, phases_override=None):
    """Helper to write a .phase-status.json."""
    run_dir = tmp_path / ".migration" / "0624-1430"
    run_dir.mkdir(parents=True, exist_ok=True)
    phases = phases_override or {
        "discover": "completed" if phase != "discover" else "in_progress",
        "clarify": "completed" if phase in ("design",) else ("in_progress" if phase == "clarify" else "pending"),
        "design": "in_progress" if phase == "design" else "pending",
    }
    status = {"migration_id": "0624-1430", "current_phase": phase, "phases": phases}
    (run_dir / ".phase-status.json").write_text(json.dumps(status))
    return run_dir


def test_router_discover_with_terraform(tmp_path, routes_config):
    """Terraform files present → iac route active, billing-full excluded, billing-lightweight included."""
    run_dir = _write_status(tmp_path, "discover")
    (tmp_path / "main.tf").touch()
    (tmp_path / "costs-billing.csv").touch()  # billing files also present

    result = phase_router(
        migration_dir=str(run_dir), project_dir=str(tmp_path), routes_config=routes_config
    )
    assert result["current_phase"] == "discover"
    route_ids = [r["id"] for r in result["routes"]]
    assert "iac" in route_ids
    assert "billing-lightweight" in route_ids
    assert "preview" in route_ids
    assert "billing-full" not in route_ids

    skipped_ids = [r["id"] for r in result["skipped_routes"]]
    assert "billing-full" in skipped_ids


def test_router_discover_billing_only(tmp_path, routes_config):
    """No Terraform, billing file present → billing-full route active, billing-lightweight skipped."""
    run_dir = _write_status(tmp_path, "discover")
    (tmp_path / "costs-billing.csv").touch()

    result = phase_router(
        migration_dir=str(run_dir), project_dir=str(tmp_path), routes_config=routes_config
    )
    route_ids = [r["id"] for r in result["routes"]]
    assert "billing-full" in route_ids
    assert "iac" not in route_ids
    assert "billing-lightweight" not in route_ids

    skipped_ids = [r["id"] for r in result["skipped_routes"]]
    assert "billing-lightweight" in skipped_ids


def test_router_discover_no_files(tmp_path, routes_config):
    """No source files → only preview (always) is active."""
    run_dir = _write_status(tmp_path, "discover")

    result = phase_router(
        migration_dir=str(run_dir), project_dir=str(tmp_path), routes_config=routes_config
    )
    route_ids = [r["id"] for r in result["routes"]]
    assert route_ids == ["preview"]


def test_router_clarify_with_inventory(tmp_path, routes_config):
    """Clarify phase + inventory exists → global route active."""
    run_dir = _write_status(tmp_path, "clarify")
    (run_dir / "inventory.json").touch()

    result = phase_router(
        migration_dir=str(run_dir), project_dir=str(tmp_path), routes_config=routes_config
    )
    route_ids = [r["id"] for r in result["routes"]]
    assert "global" in route_ids
    assert "ai-only" not in route_ids


def test_router_clarify_ai_only(tmp_path, routes_config):
    """Clarify phase + ai-profile but no inventory → ai-only route."""
    run_dir = _write_status(tmp_path, "clarify")
    (run_dir / "ai-profile.json").touch()

    result = phase_router(
        migration_dir=str(run_dir), project_dir=str(tmp_path), routes_config=routes_config
    )
    route_ids = [r["id"] for r in result["routes"]]
    assert "ai-only" in route_ids
    assert "global" not in route_ids


def test_router_requires_phase_not_met(tmp_path, routes_config):
    """Design phase but clarify not completed → error."""
    run_dir = _write_status(tmp_path, "design", phases_override={
        "discover": "completed", "clarify": "in_progress", "design": "in_progress",
    })

    result = phase_router(
        migration_dir=str(run_dir), project_dir=str(tmp_path), routes_config=routes_config
    )
    assert "error" in result
    assert "clarify" in result["error"]


def test_router_missing_status_file(tmp_path, routes_config):
    """No .phase-status.json → error."""
    run_dir = tmp_path / ".migration" / "0624-1430"
    run_dir.mkdir(parents=True)

    result = phase_router(
        migration_dir=str(run_dir), project_dir=str(tmp_path), routes_config=routes_config
    )
    assert "error" in result


def test_router_returns_file_paths(tmp_path, routes_config):
    """Routes include the file path to load."""
    run_dir = _write_status(tmp_path, "discover")
    (tmp_path / "main.tf").touch()

    result = phase_router(
        migration_dir=str(run_dir), project_dir=str(tmp_path), routes_config=routes_config
    )
    iac_route = next(r for r in result["routes"] if r["id"] == "iac")
    assert iac_route["file"] == "discover-iac.md"
    assert iac_route["produces"] == ["inventory.json"]


# --- phase_advance ---

from migration_tools.tools.orchestration import phase_advance


def test_advance_gate_passes(tmp_path, routes_config):
    """All required artifacts exist → advance to next phase."""
    run_dir = _write_status(tmp_path, "discover")
    (tmp_path / "main.tf").touch()  # so iac route is active
    (run_dir / "inventory.json").touch()  # iac produces this

    result = phase_advance(
        migration_dir=str(run_dir), project_dir=str(tmp_path), routes_config=routes_config
    )
    assert result["gate_passed"] is True
    assert result["previous_phase"] == "discover"
    assert result["advanced_to"] == "clarify"

    # Verify status file was updated
    status = json.loads((run_dir / ".phase-status.json").read_text())
    assert status["current_phase"] == "clarify"
    assert status["phases"]["discover"] == "completed"
    assert status["phases"]["clarify"] == "in_progress"


def test_advance_gate_fails_missing_artifact(tmp_path, routes_config):
    """Required artifact missing → gate fails, no advancement."""
    run_dir = _write_status(tmp_path, "discover")
    (tmp_path / "main.tf").touch()  # iac route active, but inventory.json not produced

    result = phase_advance(
        migration_dir=str(run_dir), project_dir=str(tmp_path), routes_config=routes_config
    )
    assert result["gate_passed"] is False
    assert "inventory.json" in result["missing_artifacts"]

    # Status unchanged
    status = json.loads((run_dir / ".phase-status.json").read_text())
    assert status["current_phase"] == "discover"


def test_advance_skipped_routes_not_checked(tmp_path, routes_config):
    """billing-full route excluded → its produces not checked."""
    run_dir = _write_status(tmp_path, "discover")
    (tmp_path / "main.tf").touch()  # iac active → billing-full excluded
    (tmp_path / "costs-billing.csv").touch()  # billing trigger matches but billing-full excluded
    (run_dir / "inventory.json").touch()  # iac's artifact present
    (run_dir / "billing.json").touch()  # billing-lightweight's artifact present

    result = phase_advance(
        migration_dir=str(run_dir), project_dir=str(tmp_path), routes_config=routes_config
    )
    assert result["gate_passed"] is True


def test_advance_no_produces_always_passes(tmp_path, routes_config):
    """Routes with empty produces [] don't block the gate."""
    run_dir = _write_status(tmp_path, "discover")
    # No files → only "preview" route active (produces: [])

    result = phase_advance(
        migration_dir=str(run_dir), project_dir=str(tmp_path), routes_config=routes_config
    )
    assert result["gate_passed"] is True
    assert result["advanced_to"] == "clarify"


def test_advance_last_phase(tmp_path, routes_config):
    """Advancing from the last defined phase → complete."""
    # Add a feedback phase to the test config
    routes_config["routes"]["feedback"] = {
        "routes": [{"id": "default", "trigger": {"always": True}, "file": "feedback.md", "produces": []}]
    }
    routes_config["phases"] = ["discover", "clarify", "design", "feedback"]
    run_dir = _write_status(tmp_path, "feedback", phases_override={
        "discover": "completed", "clarify": "completed", "design": "completed", "feedback": "in_progress",
    })

    result = phase_advance(
        migration_dir=str(run_dir), project_dir=str(tmp_path), routes_config=routes_config
    )
    assert result["gate_passed"] is True
    assert result["advanced_to"] == "complete"


def test_advance_missing_status_file(tmp_path, routes_config):
    """No status file → error."""
    run_dir = tmp_path / ".migration" / "0624-1430"
    run_dir.mkdir(parents=True)

    result = phase_advance(
        migration_dir=str(run_dir), project_dir=str(tmp_path), routes_config=routes_config
    )
    assert "error" in result
