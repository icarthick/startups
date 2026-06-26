"""Phase orchestration tools — state management, routing, and gates."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("engine.phase")


def migration_status(project_dir: str) -> dict[str, Any]:
    """List existing migration runs in a project."""
    root = Path(project_dir) / ".migration"
    if not root.is_dir():
        logger.info("No .migration/ directory in %s", project_dir)
        return {"runs": [], "message": "No .migration/ directory found"}

    runs = []
    for run_dir in sorted(root.iterdir()):
        if not run_dir.is_dir():
            continue
        status_file = run_dir / ".phase-status.json"
        if status_file.exists():
            with open(status_file) as f:
                status = json.load(f)
            runs.append({"id": run_dir.name, "path": str(run_dir), **status})
        else:
            runs.append({"id": run_dir.name, "path": str(run_dir), "status": "unknown"})

    logger.info("Found %d migration run(s) in %s", len(runs), project_dir)
    return {"runs": runs}


def migration_init(project_dir: str, skill: str = "heroku-to-aws") -> dict[str, Any]:
    """Create a new migration run."""
    root = Path(project_dir) / ".migration"
    run_id = datetime.now().strftime("%m%d-%H%M")
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Created migration run: %s", run_dir)

    # Write .gitignore
    gitignore = root / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*\n")

    # Determine phases from a default set
    phases = ["discover", "clarify", "design", "estimate", "generate", "feedback"]

    status = {
        "migration_id": run_id,
        "skill": skill,
        "current_phase": "discover",
        "phases": {phases[0]: "in_progress", **{p: "pending" for p in phases[1:]}},
    }
    (run_dir / ".phase-status.json").write_text(json.dumps(status, indent=2))

    return {"status": "ok", "migration_id": run_id, "path": str(run_dir)}


def _read_status(migration_dir: str) -> dict:
    """Read .phase-status.json from a migration directory."""
    status_file = Path(migration_dir) / ".phase-status.json"
    if not status_file.exists():
        return {}
    with open(status_file) as f:
        return json.load(f)


def _write_status(migration_dir: str, status: dict) -> None:
    """Write .phase-status.json to a migration directory."""
    status_file = Path(migration_dir) / ".phase-status.json"
    with open(status_file, "w") as f:
        json.dump(status, f, indent=2)


def _glob_matches(project_dir: str, patterns: list[str]) -> bool:
    """Check if any glob pattern matches files in project_dir."""
    root = Path(project_dir)
    for pattern in patterns:
        if list(root.rglob(pattern)):
            return True
    return False


def _artifact_exists(migration_dir: str, artifacts: list[str]) -> bool:
    """Check if all listed artifacts exist in migration_dir."""
    mdir = Path(migration_dir)
    return all((mdir / a).exists() for a in artifacts)


def _artifact_absent(migration_dir: str, artifacts: list[str]) -> bool:
    """Check that none of the listed artifacts exist."""
    mdir = Path(migration_dir)
    return all(not (mdir / a).exists() for a in artifacts)


def phase_router(migration_dir: str, project_dir: str, routes_config: dict) -> dict[str, Any]:
    """Evaluate routes for the current phase, return files to load."""
    status = _read_status(migration_dir)
    if not status:
        return {"error": "No .phase-status.json found"}

    current_phase = status.get("current_phase", "")
    phase_config = routes_config.get("routes", {}).get(current_phase)
    if not phase_config:
        return {"error": f"No routes defined for phase '{current_phase}'"}

    # Check phase prerequisite
    requires = phase_config.get("requires_phase")
    if requires:
        if status.get("phases", {}).get(requires) != "completed":
            return {"error": f"Phase '{current_phase}' requires '{requires}' to be completed"}

    # Evaluate route triggers
    active_routes = []
    skipped_routes = []
    active_ids = set()

    routes = phase_config.get("routes", [])

    # First pass: evaluate triggers
    triggered = []
    for route in routes:
        trigger = route.get("trigger", {})
        matched = False

        if trigger.get("always"):
            matched = True
        elif "glob" in trigger:
            matched = _glob_matches(project_dir, trigger["glob"])
        elif "artifact_exists" in trigger:
            matched = _artifact_exists(migration_dir, trigger["artifact_exists"])
            if matched and "artifact_absent" in trigger:
                matched = _artifact_absent(migration_dir, trigger["artifact_absent"])

        if matched:
            triggered.append(route)
        else:
            skipped_routes.append({"id": route["id"], "reason": "trigger_not_matched"})

    # Second pass: apply conditional routing
    triggered_ids = {r["id"] for r in triggered}
    for route in triggered:
        do_not_run = route.get("do_not_run_with_routes", [])
        run_only = route.get("run_only_with_routes", [])

        if do_not_run and any(rid in triggered_ids for rid in do_not_run):
            skipped_routes.append({"id": route["id"], "reason": f"excluded_by_{do_not_run}"})
            continue
        if run_only and not any(rid in triggered_ids for rid in run_only):
            skipped_routes.append({"id": route["id"], "reason": f"requires_{run_only}"})
            continue

        active_routes.append(route)
        active_ids.add(route["id"])

    return {
        "current_phase": current_phase,
        "routes": active_routes,
        "skipped_routes": skipped_routes,
    }


def phase_advance(migration_dir: str, project_dir: str, routes_config: dict) -> dict[str, Any]:
    """Validate gate and advance to next phase."""
    status = _read_status(migration_dir)
    if not status:
        return {"error": "No .phase-status.json found"}

    current_phase = status.get("current_phase", "")
    phases = routes_config.get("phases", [])
    logger.info("phase_advance: validating gate for phase '%s'", current_phase)

    # Check gate: all active routes' produces must exist
    router_result = phase_router(migration_dir, project_dir, routes_config)
    if "error" in router_result:
        return router_result

    missing = []
    for route in router_result["routes"]:
        for artifact in route.get("produces", []):
            if artifact and not _artifact_exists(migration_dir, [artifact]):
                missing.append({"route": route["id"], "artifact": artifact})

    if missing:
        return {"status": "gate_failed", "missing_artifacts": missing}

    # Advance
    current_idx = phases.index(current_phase) if current_phase in phases else -1
    if current_idx < 0 or current_idx >= len(phases) - 1:
        return {"status": "completed", "message": "All phases complete"}

    next_phase = phases[current_idx + 1]
    status["phases"][current_phase] = "completed"
    status["phases"][next_phase] = "in_progress"
    status["current_phase"] = next_phase
    _write_status(migration_dir, status)

    return {"status": "advanced", "from": current_phase, "to": next_phase}


def phase_reset(migration_dir: str, from_phase: str, routes_config: dict) -> dict[str, Any]:
    """Reset a phase and all downstream phases for re-entry."""
    status = _read_status(migration_dir)
    if not status:
        return {"error": "No .phase-status.json found"}

    phases = routes_config.get("phases", [])
    if from_phase not in phases:
        return {"error": f"Unknown phase: {from_phase}"}

    from_idx = phases.index(from_phase)
    for i, phase in enumerate(phases):
        if i < from_idx:
            continue
        elif i == from_idx:
            status["phases"][phase] = "in_progress"
        else:
            status["phases"][phase] = "pending"

    status["current_phase"] = from_phase
    _write_status(migration_dir, status)

    return {"status": "reset", "current_phase": from_phase}
