"""MCP Server entrypoint for migration orchestrator.

Exposes phase orchestration tools (routing, state management, gates).
Local to this plugin — serves the skills within migration-to-aws.

Run via: python -m migration_tools.orchestrator_server
"""

import logging
import os
from pathlib import Path

from fastmcp import FastMCP

from migration_orchestrator.knowledge import load_knowledge
from migration_orchestrator.tools.orchestration import (
    migration_status as _migration_status,
    migration_init as _migration_init,
    phase_router as _phase_router,
    phase_advance as _phase_advance,
    phase_reset as _phase_reset,
)
from migration_orchestrator.tools.detect_ai_signals import detect_ai_signals as _detect_ai_signals
from migration_orchestrator.tools.cluster_terraform import cluster_terraform as _cluster_terraform
from migration_orchestrator.tools.create_ai_profile import create_ai_profile_from_iac as _create_ai_profile_from_iac

# Resolve knowledge directory
KNOWLEDGE_DIR = Path(os.environ.get(
    "MIGRATION_ORCHESTRATOR_KNOWLEDGE_DIR",
    Path(__file__).resolve().parents[2] / "knowledge"
))

# Configure logging
LOG_FILE = Path(__file__).resolve().parents[2] / "migration-orchestrator.log"
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
mcp = FastMCP("migration-plugin", instructions="Plugin-local tools: phase orchestration, source-specific discovery (GCP classification, clustering, AI detection), and file management.")


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
    routes_key = f"{skill}/routes"
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
    routes_key = f"{skill}/routes"
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
    routes_key = f"{skill}/routes"
    routes_config = _knowledge.get(routes_key)
    if not routes_config:
        return {"error": f"No routes.json found for skill '{skill}' (expected key: {routes_key})"}
    return _phase_reset(migration_dir=migration_dir, project_dir=project_dir, from_phase=from_phase, routes_config=routes_config)


@mcp.tool()
def detect_ai_signals(resources: list[dict]) -> dict:
    """Detect AI workload signals from a list of Terraform resources.

    Scans resource types and names against known AI service patterns.

    Args:
        resources: Flat list of resources extracted from Terraform.
    """
    return _detect_ai_signals(resources=resources)


@mcp.tool()
def cluster_terraform(
    resources: list[dict],
    migration_dir: str | None = None,
    ai_detection: dict | None = None,
    metadata: dict | None = None,
) -> dict:
    """Classify, build edges, compute depth, cluster, and write output files.

    Full discovery pipeline for Terraform resources.

    Args:
        resources: Flat list from Terraform parsing (address, type, name, config, depends_on).
        migration_dir: If provided, writes output files to this directory.
        ai_detection: Output from detect_ai_signals (included in inventory).
        metadata: Report metadata (report_date, project_directory, terraform_version).
    """
    return _cluster_terraform(
        resources=resources, migration_dir=migration_dir,
        ai_detection=ai_detection, metadata=metadata, knowledge=_knowledge,
    )


@mcp.tool()
def create_ai_profile_from_iac(
    ai_source: str,
    ai_detection: dict,
    vertex_resources: list[dict],
    migration_dir: str,
) -> dict:
    """Write ai-workload-profile.json from IaC-inferred Vertex AI signals.

    Args:
        ai_source: "gemini" (generative) or "other" (traditional ML).
        ai_detection: Output from detect_ai_signals tool.
        vertex_resources: Vertex AI resources (google_vertex_ai_* types).
        migration_dir: Path to write ai-workload-profile.json.
    """
    return _create_ai_profile_from_iac(
        ai_source=ai_source, ai_detection=ai_detection,
        vertex_resources=vertex_resources, migration_dir=migration_dir,
    )


if __name__ == "__main__":
    mcp.run()
