"""MCP Server for migration engine.

Exposes phase orchestration, discovery, and design tools.
"""

import logging
import sys
import tempfile
from pathlib import Path

from fastmcp import FastMCP

from engine.knowledge import load_knowledge, default_knowledge_dir
from engine.tools.orchestration import (
    migration_status as _migration_status,
    migration_init as _migration_init,
    phase_router as _phase_router,
    phase_advance as _phase_advance,
    phase_reset as _phase_reset,
)
from engine.tools.scan_heroku_terraform import scan_heroku_terraform as _scan_heroku_terraform
from engine.tools.extract_heroku_billing import extract_heroku_billing as _extract_heroku_billing
from engine.tools.design_heroku import design_heroku_migration as _design_heroku_migration
from engine.tools.estimate_heroku import estimate_heroku_migration as _estimate_heroku_migration
from engine.tools.generate_terraform import generate_terraform as _generate_terraform
from engine.tools.generate_docs import generate_docs as _generate_docs

KNOWLEDGE_DIR = default_knowledge_dir()

# Configure logging
LOG_FILE = Path(tempfile.gettempdir()) / "engine.log"
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="a"),
        logging.StreamHandler(sys.stderr),
    ],
)
logging.getLogger().handlers[1].setLevel(logging.WARNING)
logger = logging.getLogger("engine.server")
logger.warning("engine logs: %s", LOG_FILE)

# Load knowledge
logger.info("Loading knowledge from: %s", KNOWLEDGE_DIR)
_knowledge = load_knowledge(KNOWLEDGE_DIR)
logger.info("Knowledge loaded: %d files", len(_knowledge))

# Create MCP server
mcp = FastMCP("engine", instructions="Migration engine — phase orchestration, discovery, and design tools.")


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


@mcp.tool()
def scan_heroku_terraform(project_dir: str, migration_dir: str | None = None) -> dict:
    """Scan Terraform files for Heroku resources and produce discovery output.

    Parses .tf files for heroku_* resources, extracts attributes, resolves
    cross-references, integrates Procfile/app.json, detects Cedar/Fir
    generation, and writes _terraform-discovery.json.

    Args:
        project_dir: Absolute path to the project root.
        migration_dir: If provided, writes _terraform-discovery.json here.
    """
    return _scan_heroku_terraform(project_dir=project_dir, migration_dir=migration_dir)


@mcp.tool()
def extract_heroku_billing(project_dir: str, migration_dir: str | None = None) -> dict:
    """Extract billing summary from Heroku billing exports.

    Parses Enterprise CSV, Dashboard invoice CSV/JSON, and API invoice JSON.
    Produces per-app cost breakdown and writes _billing-discovery.json.

    Args:
        project_dir: Absolute path to the project root.
        migration_dir: If provided, writes _billing-discovery.json here.
    """
    return _extract_heroku_billing(project_dir=project_dir, migration_dir=migration_dir)


@mcp.tool()
def design_heroku_migration(migration_dir: str) -> dict:
    """Design AWS architecture from Heroku resource inventory.

    Reads heroku-resource-inventory.json and preferences.json, applies
    deterministic mapping tables (dyno→Fargate, postgres→RDS/Aurora,
    redis→ElastiCache, kafka→MSK, fast-path addons), generates VPC
    design, and writes aws-design.json.

    Args:
        migration_dir: Path to the migration run directory.
    """
    return _design_heroku_migration(migration_dir=migration_dir, knowledge=_knowledge)


@mcp.tool()
def estimate_heroku_migration(migration_dir: str) -> dict:
    """Estimate AWS costs for the designed Heroku migration.

    Calculates per-service monthly costs using cached pricing, generates
    cost comparison with Heroku baseline, classifies complexity tier, and
    writes estimation-infra.json.

    Args:
        migration_dir: Path to the migration run directory.
    """
    return _estimate_heroku_migration(migration_dir=migration_dir, knowledge=_knowledge)


@mcp.tool()
def generate_terraform(migration_dir: str) -> dict:
    """Generate Terraform files from aws-design.json using templates.

    Reads the design, picks templates per service type, substitutes values,
    and writes .tf files to migration_dir/terraform/.

    Args:
        migration_dir: Path to the migration run directory.
    """
    return _generate_terraform(migration_dir=migration_dir, knowledge=_knowledge)


@mcp.tool()
def generate_docs(migration_dir: str) -> dict:
    """Generate migration documentation and scripts.

    Produces MIGRATION_GUIDE.md, README.md, and database migration scripts
    (migrate-postgres.sh, migrate-redis.sh) based on the design.

    Args:
        migration_dir: Path to the migration run directory.
    """
    return _generate_docs(migration_dir=migration_dir, knowledge=_knowledge)


if __name__ == "__main__":
    mcp.run()
