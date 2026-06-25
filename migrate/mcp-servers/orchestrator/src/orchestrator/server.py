"""MCP Server entrypoint for orchestrator.

Exposes phase orchestration tools (routing, state management, gates).
"""

import logging
import sys
import tempfile
from pathlib import Path

from fastmcp import FastMCP

from orchestrator.knowledge import load_knowledge, default_knowledge_dir
from orchestrator.tools.orchestration import (
    migration_status as _migration_status,
    migration_init as _migration_init,
    phase_router as _phase_router,
    phase_advance as _phase_advance,
    phase_reset as _phase_reset,
)

KNOWLEDGE_DIR = default_knowledge_dir()

# Configure logging
LOG_FILE = Path(tempfile.gettempdir()) / "orchestrator.log"
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="a"),
        logging.StreamHandler(sys.stderr),
    ],
)
logging.getLogger().handlers[1].setLevel(logging.WARNING)
logger = logging.getLogger("orchestrator.server")
logger.warning("orchestrator logs: %s", LOG_FILE)

# Load knowledge
logger.info("Loading knowledge from: %s", KNOWLEDGE_DIR)
_knowledge = load_knowledge(KNOWLEDGE_DIR)
logger.info("Knowledge loaded: %d files", len(_knowledge))

# Create MCP server
mcp = FastMCP("orchestrator", instructions="Phase orchestration for migration workflows — routing, state management, gates.")


@mcp.tool()
def migration_status(project_dir: str) -> dict:
    """List existing migration runs in a project.

    Args:
        project_dir: Absolute path to the project root directory.
    """
    return _migration_status(project_dir=project_dir)


@mcp.tool()
def migration_init(project_dir: str, skill: str = "heroku-to-aws") -> dict:
    """Create a new migration run.

    Args:
        project_dir: Absolute path to the project root directory.
        skill: Skill name (e.g., heroku-to-aws, gcp-to-aws).
    """
    return _migration_init(project_dir=project_dir, skill=skill)


@mcp.tool()
def phase_router(migration_dir: str, project_dir: str, skill: str = "heroku-to-aws") -> dict:
    """Determine which phase files to load for the current migration phase.

    Args:
        migration_dir: Path to the migration run directory.
        project_dir: Absolute path to the project root directory.
        skill: Skill name to load routes for.
    """
    routes_key = f"{skill}/routes"
    routes_config = _knowledge.get(routes_key)
    if not routes_config:
        return {"error": f"No routes.json found for skill '{skill}'"}
    return _phase_router(migration_dir=migration_dir, project_dir=project_dir, routes_config=routes_config)


@mcp.tool()
def phase_advance(migration_dir: str, project_dir: str, skill: str = "heroku-to-aws") -> dict:
    """Validate the current phase gate and advance to the next phase.

    Args:
        migration_dir: Path to the migration run directory.
        project_dir: Absolute path to the project root directory.
        skill: Skill name to load routes for.
    """
    routes_key = f"{skill}/routes"
    routes_config = _knowledge.get(routes_key)
    if not routes_config:
        return {"error": f"No routes.json found for skill '{skill}'"}
    return _phase_advance(migration_dir=migration_dir, project_dir=project_dir, routes_config=routes_config)


@mcp.tool()
def phase_reset(migration_dir: str, from_phase: str, skill: str = "heroku-to-aws") -> dict:
    """Reset a phase and all downstream phases for re-entry.

    Args:
        migration_dir: Path to the migration run directory.
        from_phase: Phase to reset from.
        skill: Skill name to load routes for.
    """
    routes_key = f"{skill}/routes"
    routes_config = _knowledge.get(routes_key)
    if not routes_config:
        return {"error": f"No routes.json found for skill '{skill}'"}
    return _phase_reset(migration_dir=migration_dir, from_phase=from_phase, routes_config=routes_config)


if __name__ == "__main__":
    mcp.run()
