"""MCP Server entrypoint for migration orchestrator.

Exposes phase orchestration tools (routing, state management, gates).
Local to this plugin — serves the skills within migration-to-aws.

Run via: python -m migration_tools.orchestrator_server
"""

import logging
import os
from pathlib import Path

from fastmcp import FastMCP

from migration_tools.knowledge import load_knowledge
from migration_tools.tools.orchestration import (
    migration_status as _migration_status,
    migration_init as _migration_init,
    phase_router as _phase_router,
    phase_advance as _phase_advance,
    phase_reset as _phase_reset,
)

# Resolve knowledge directory
KNOWLEDGE_DIR = Path(os.environ.get(
    "MIGRATION_TOOLS_KNOWLEDGE_DIR",
    Path(__file__).resolve().parents[3] / "knowledge"
))

# Configure logging
LOG_FILE = Path(__file__).resolve().parents[3] / "server" / "migration-orchestrator.log"
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, mode="a")],
)
logger = logging.getLogger("migration_tools.orchestrator")

# Load knowledge (only needs orchestration/ subtree, but loads all for simplicity)
logger.info("Loading knowledge store from: %s", KNOWLEDGE_DIR)
_knowledge = load_knowledge(KNOWLEDGE_DIR)
logger.info("Knowledge store loaded: %d files", len(_knowledge))

# Create MCP server
mcp = FastMCP("migration-orchestrator", instructions="Phase orchestration tools for migration skills. Handles routing, state management, and gate validation.")


@mcp.tool()
def migration_status(project_dir: str) -> dict:
    """List existing migration runs in a project.

    Scans .migration/ for existing runs and returns their phase status.
    Use at the start of a migration conversation to check for resumable runs.

    Args:
        project_dir: Absolute path to the project root directory.
    """
    return _migration_status(project_dir=project_dir)


@mcp.tool()
def migration_init(project_dir: str) -> dict:
    """Create a new migration run.

    Creates .migration/[MMDD-HHMM]/ with .gitignore and initial .phase-status.json.
    The discover phase is set to in_progress.

    Args:
        project_dir: Absolute path to the project root directory.
    """
    return _migration_init(project_dir=project_dir)


@mcp.tool()
def phase_router(
    migration_dir: str,
    project_dir: str,
    skill: str = "gcp-to-aws",
) -> dict:
    """Determine which phase files to load for the current migration phase.

    Reads the migration status and evaluates route triggers (file globs,
    artifact existence) to determine which sub-files the LLM should load
    and execute.

    Args:
        migration_dir: Path to the migration run directory (e.g., .migration/0624-1430).
        project_dir: Absolute path to the project root directory.
        skill: Skill name to load routes for (e.g., gcp-to-aws, heroku-to-aws).
    """
    routes_key = f"orchestration/{skill}/routes"
    routes_config = _knowledge.get(routes_key)
    if not routes_config:
        return {"error": f"No routes.json found for skill '{skill}' (expected key: {routes_key})"}
    return _phase_router(migration_dir=migration_dir, project_dir=project_dir, routes_config=routes_config)


@mcp.tool()
def phase_advance(
    migration_dir: str,
    project_dir: str,
    skill: str = "gcp-to-aws",
) -> dict:
    """Validate the current phase gate and advance to the next phase.

    Checks that all required artifacts from active routes exist. If the gate
    passes, marks the current phase completed and the next phase in_progress.

    Args:
        migration_dir: Path to the migration run directory.
        project_dir: Absolute path to the project root directory.
        skill: Skill name to load routes for.
    """
    routes_key = f"orchestration/{skill}/routes"
    routes_config = _knowledge.get(routes_key)
    if not routes_config:
        return {"error": f"No routes.json found for skill '{skill}' (expected key: {routes_key})"}
    return _phase_advance(migration_dir=migration_dir, project_dir=project_dir, routes_config=routes_config)


@mcp.tool()
def phase_reset(
    migration_dir: str,
    project_dir: str,
    from_phase: str,
    skill: str = "gcp-to-aws",
) -> dict:
    """Reset a phase and all downstream phases for re-entry.

    Use when a user wants to re-run a previously completed phase. Sets the
    target phase to in_progress and all downstream phases to pending.

    Args:
        migration_dir: Path to the migration run directory.
        project_dir: Absolute path to the project root directory.
        from_phase: Phase to reset from (e.g., "discover"). This phase becomes in_progress.
        skill: Skill name to load routes for.
    """
    routes_key = f"orchestration/{skill}/routes"
    routes_config = _knowledge.get(routes_key)
    if not routes_config:
        return {"error": f"No routes.json found for skill '{skill}' (expected key: {routes_key})"}
    return _phase_reset(migration_dir=migration_dir, project_dir=project_dir, from_phase=from_phase, routes_config=routes_config)


if __name__ == "__main__":
    mcp.run()
