"""MCP Server entrypoint.

Exposes migration tools via FastMCP. Loads the knowledge store at startup.
Run via: uvx migration-tools serve  (or: python -m migration_tools.server)
"""

import logging
from pathlib import Path

from fastmcp import FastMCP

from migration_tools.knowledge import load_knowledge
from migration_tools.tools.recommend_database import recommend_database_target

# Resolve knowledge directory (relative to server source)
KNOWLEDGE_DIR = Path(__file__).resolve().parents[3] / "knowledge"

# Configure logging — writes to a file next to the server for easy inspection
LOG_FILE = Path(__file__).resolve().parents[3] / "server" / "migration-tools.log"
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="a"),
    ],
)
logger = logging.getLogger("migration_tools.server")

# Load knowledge store at startup
logger.info("Loading knowledge store from: %s", KNOWLEDGE_DIR)
_knowledge = load_knowledge(KNOWLEDGE_DIR)
logger.info("Knowledge store loaded: %d files", len(_knowledge))

# Create MCP server
mcp = FastMCP("migration-tools", instructions="Deterministic migration recommendation tools backed by structured knowledge.")


@mcp.tool()
def recommend_database(
    engine: str,
    availability: str | None = None,
    size_class: str = "micro",
    io_workload: str = "low",
    traffic: str = "steady",
    data_size_gb: float | None = None,
) -> dict:
    """Recommend an AWS database target for a relational database migration.

    Given canonical workload attributes (engine, availability requirement, size,
    I/O intensity, traffic pattern, data size), returns a complete AWS database
    recommendation including service, instance sizing, storage type, replica
    config, and migration tooling.

    Args:
        engine: Database engine (postgres, mysql, sqlserver).
        availability: HA requirement (single-az, multi-az, multi-az-ha, multi-region). Omit to get a clarification request.
        size_class: Workload size (micro, small, medium, large, xlarge).
        io_workload: I/O intensity (low, medium, high).
        traffic: Traffic pattern (steady, read-heavy, write-heavy, spiky).
        data_size_gb: Database size in GB (for migration tool selection).
    """
    return recommend_database_target(
        engine=engine,
        availability=availability,
        size_class=size_class,
        io_workload=io_workload,
        traffic=traffic,
        data_size_gb=data_size_gb,
        knowledge=_knowledge,
    )


if __name__ == "__main__":
    mcp.run()
