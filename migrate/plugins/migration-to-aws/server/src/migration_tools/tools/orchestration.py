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
