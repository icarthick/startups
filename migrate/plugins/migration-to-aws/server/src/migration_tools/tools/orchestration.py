"""Orchestration tools — phase state machine, routing, and lifecycle management.

These tools manage the migration lifecycle: init, status, routing, and advancement.
They read routes.json configs and .phase-status.json to provide deterministic
orchestration that any skill (gcp-to-aws, heroku-to-aws, etc.) can reuse.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("migration_tools.orchestration")

VALID_PHASES = {"discover", "clarify", "design", "estimate", "generate", "feedback"}
VALID_STATUSES = {"pending", "in_progress", "completed"}
PHASE_ORDER = ["discover", "clarify", "design", "estimate", "generate", "feedback"]

GITIGNORE_CONTENT = "# Auto-generated migration state (temporary, do not commit)\n*\n!.gitignore\n"

INITIAL_STATUS = {
    "discover": "in_progress",
    "clarify": "pending",
    "design": "pending",
    "estimate": "pending",
    "generate": "pending",
    "feedback": "pending",
}


def migration_status(project_dir: str) -> dict:
    """List existing migration runs and their phase status.

    Args:
        project_dir: Path to the project root (where .migration/ lives).

    Returns:
        {"migrations": [...], "latest": "MMDD-HHMM" or null}
    """
    migration_root = Path(project_dir) / ".migration"

    if not migration_root.exists():
        return {"migrations": [], "latest": None}

    migrations = []
    for entry in sorted(migration_root.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue

        status_file = entry / ".phase-status.json"
        if not status_file.exists():
            migrations.append({
                "id": entry.name,
                "dir": str(entry.relative_to(project_dir)),
                "current_phase": None,
                "phases": None,
                "error": "Missing .phase-status.json",
            })
            continue

        try:
            status = json.loads(status_file.read_text())
        except json.JSONDecodeError:
            migrations.append({
                "id": entry.name,
                "dir": str(entry.relative_to(project_dir)),
                "current_phase": None,
                "phases": None,
                "error": "Invalid JSON in .phase-status.json",
            })
            continue

        migrations.append({
            "id": entry.name,
            "dir": str(entry.relative_to(project_dir)),
            "current_phase": status.get("current_phase"),
            "phases": status.get("phases"),
            "last_updated": status.get("last_updated"),
        })

    latest = migrations[-1]["id"] if migrations else None
    return {"migrations": migrations, "latest": latest}


def migration_init(project_dir: str) -> dict:
    """Create a new migration run directory with initial state.

    Args:
        project_dir: Path to the project root.

    Returns:
        {"migration_id": "MMDD-HHMM", "migration_dir": "...", "current_phase": "discover", "status": "initialized"}
    """
    migration_root = Path(project_dir) / ".migration"
    migration_root.mkdir(exist_ok=True)

    # Write .gitignore if not present
    gitignore = migration_root / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(GITIGNORE_CONTENT)

    # Create timestamped directory
    now = datetime.now()
    migration_id = now.strftime("%m%d-%H%M")
    migration_dir = migration_root / migration_id
    migration_dir.mkdir(exist_ok=True)

    # Write initial .phase-status.json
    status = {
        "migration_id": migration_id,
        "last_updated": now.isoformat(),
        "current_phase": "discover",
        "phases": dict(INITIAL_STATUS),
    }
    (migration_dir / ".phase-status.json").write_text(json.dumps(status, indent=2) + "\n")

    logger.info("migration_init: created %s", migration_dir)

    return {
        "migration_id": migration_id,
        "migration_dir": str(migration_dir.relative_to(project_dir)),
        "current_phase": "discover",
        "status": "initialized",
    }


def _evaluate_trigger(trigger: dict, project_dir: Path, migration_dir: Path) -> bool:
    """Evaluate a route trigger condition.

    Trigger types:
      - {"always": true} → always active
      - {"glob": [...]} → at least one glob matches a file in project_dir
      - {"artifact_exists": [...]} → all listed artifacts exist in migration_dir
      - {"artifact_absent": [...]} → none of the listed artifacts exist in migration_dir
    Multiple conditions in one trigger are AND'd together.
    """
    if trigger.get("always"):
        return True

    result = True

    if "glob" in trigger:
        glob_match = False
        for pattern in trigger["glob"]:
            if list(project_dir.glob(pattern)):
                glob_match = True
                break
        if not glob_match:
            result = False

    if "artifact_exists" in trigger and result:
        for artifact in trigger["artifact_exists"]:
            if not (migration_dir / artifact).exists():
                result = False
                break

    if "artifact_absent" in trigger and result:
        for artifact in trigger["artifact_absent"]:
            if (migration_dir / artifact).exists():
                result = False
                break

    return result


def phase_router(
    migration_dir: str,
    project_dir: str,
    routes_config: dict,
) -> dict:
    """Determine which route files to load for the current phase.

    Args:
        migration_dir: Path to the migration run directory (e.g., .migration/0624-1430).
        project_dir: Path to the project root.
        routes_config: The routes.json content (loaded from knowledge store).

    Returns:
        {"current_phase": str, "routes": [...], "skipped_routes": [...]}
        or {"error": str} if prerequisites not met.
    """
    migration_path = Path(migration_dir) if Path(migration_dir).is_absolute() else Path(project_dir) / migration_dir
    project_path = Path(project_dir)

    # Read current phase
    status_file = migration_path / ".phase-status.json"
    if not status_file.exists():
        return {"error": f"No .phase-status.json in {migration_dir}"}

    try:
        status = json.loads(status_file.read_text())
    except json.JSONDecodeError:
        return {"error": "Invalid JSON in .phase-status.json"}

    current_phase = status.get("current_phase")
    if current_phase not in routes_config.get("routes", {}):
        return {"error": f"No routes defined for phase '{current_phase}'"}

    phase_config = routes_config["routes"][current_phase]

    # Check requires_phase prerequisite
    requires = phase_config.get("requires_phase")
    if requires:
        phases = status.get("phases", {})
        if phases.get(requires) != "completed":
            return {
                "error": f"Phase '{current_phase}' requires '{requires}' to be completed. Current status: '{phases.get(requires, 'unknown')}'",
            }

    # Evaluate each route's trigger
    active_routes = []
    skipped_routes = []
    active_ids = set()

    for route in phase_config.get("routes", []):
        trigger = route.get("trigger", {})
        if _evaluate_trigger(trigger, project_path, migration_path):
            active_routes.append(route)
            active_ids.add(route["id"])
        else:
            skipped_routes.append({"id": route["id"], "reason": "Trigger not met"})

    # Apply excludes_if_active
    final_routes = []
    for route in active_routes:
        excludes = route.get("excludes_if_active", [])
        if any(ex_id in active_ids for ex_id in excludes):
            skipped_routes.append({
                "id": route["id"],
                "reason": f"Excluded because {[e for e in excludes if e in active_ids]} is active",
            })
        else:
            final_routes.append({
                "id": route["id"],
                "file": route["file"],
                "produces": route.get("produces", []),
            })

    logger.info("phase_router: phase=%s, active=%s, skipped=%s",
                current_phase, [r["id"] for r in final_routes], [r["id"] for r in skipped_routes])

    return {
        "current_phase": current_phase,
        "routes": final_routes,
        "skipped_routes": skipped_routes,
    }
