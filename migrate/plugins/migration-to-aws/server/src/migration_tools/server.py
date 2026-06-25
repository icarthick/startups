"""MCP Server entrypoint.

Exposes migration tools via FastMCP. Loads the knowledge store at startup.
Run via: uvx migration-tools serve  (or: python -m migration_tools.server)
"""

import logging
from pathlib import Path

from fastmcp import FastMCP

from migration_tools.knowledge import load_knowledge
from migration_tools.tools.recommend_database import recommend_database_target
from migration_tools.tools.recommend_compute import recommend_compute_target
from migration_tools.tools.recommend_networking import recommend_networking_target
from migration_tools.tools.recommend_messaging import recommend_messaging_target
from migration_tools.tools.normalize import normalize_resource as _normalize_resource
from migration_tools.tools.lookup_direct import lookup_direct_mapping as _lookup_direct_mapping
from migration_tools.tools.validate_design import validate_design as _validate_design
from migration_tools.tools.orchestration import (
    migration_status as _migration_status,
    migration_init as _migration_init,
    phase_router as _phase_router,
    phase_advance as _phase_advance,
    phase_reset as _phase_reset,
)

# Resolve knowledge directory — prefer env var (set by .mcp.json), fallback to relative for dev
import os
KNOWLEDGE_DIR = Path(os.environ.get(
    "MIGRATION_TOOLS_KNOWLEDGE_DIR",
    Path(__file__).resolve().parents[3] / "knowledge"
))

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


@mcp.tool()
def recommend_compute(
    service_type: str,
    timeout_seconds: int | None = None,
    vcpu: float = 0.25,
    memory_gb: float = 0.5,
    gpu: bool = False,
    runtime: str | None = None,
    workload_pattern: str | None = None,
    kubernetes_pref: str | None = None,
    cost_sensitivity: str | None = None,
) -> dict:
    """Recommend an AWS compute target for a workload migration.

    Given canonical compute attributes (service type, resource specs, preferences,
    workload pattern), returns AWS service selection + validated sizing.

    Args:
        service_type: Canonical workload type (container, function, vm, kubernetes, app-engine).
        timeout_seconds: Max execution/request timeout in seconds.
        vcpu: Source vCPU count.
        memory_gb: Source memory in GB.
        gpu: Whether GPU is required.
        runtime: Language runtime (for functions, e.g. python39, nodejs18).
        workload_pattern: LLM-inferred pattern (always-on, event-driven, batch, windows-only). Null if undetermined.
        kubernetes_pref: User's K8s preference from Clarify (eks-managed, eks-or-ecs, ecs-fargate, or null).
        cost_sensitivity: User's cost sensitivity (high, medium, low, or null).
    """
    return recommend_compute_target(
        service_type=service_type,
        timeout_seconds=timeout_seconds,
        vcpu=vcpu,
        memory_gb=memory_gb,
        gpu=gpu,
        runtime=runtime,
        workload_pattern=workload_pattern,
        kubernetes_pref=kubernetes_pref,
        cost_sensitivity=cost_sensitivity,
        knowledge=_knowledge,
    )


@mcp.tool()
def recommend_networking(
    protocol: str | None = None,
    scheme: str | None = None,
    port_range: str | None = None,
    performance_priority: str | None = None,
) -> dict:
    """Recommend an AWS load balancer target for a networking migration.

    Given canonical networking attributes (protocol, scheme, port range),
    returns ALB or NLB recommendation with configuration.

    Args:
        protocol: Traffic protocol (HTTP, HTTPS, TCP, UDP). Primary decision signal.
        scheme: Load balancer scheme (EXTERNAL, INTERNAL).
        port_range: Port or port range (e.g., "80", "443", "8080-8090").
        performance_priority: Optional priority signal (ultra-low-latency favors NLB).
    """
    return recommend_networking_target(
        protocol=protocol,
        scheme=scheme,
        port_range=port_range,
        performance_priority=performance_priority,
        knowledge=_knowledge,
    )


@mcp.tool()
def recommend_messaging(
    delivery_pattern: str | None = None,
    subscriber_count: int | None = None,
    ordering_required: bool | None = None,
    ack_deadline_seconds: int | None = None,
) -> dict:
    """Recommend an AWS messaging target for a message broker migration.

    Given canonical messaging attributes (delivery pattern, subscriber count,
    ordering requirement), returns SNS+SQS or SQS-only recommendation.

    Args:
        delivery_pattern: Message delivery pattern (fan-out, point-to-point).
        subscriber_count: Number of consumers/subscribers. >1 implies fan-out.
        ordering_required: Whether message ordering must be preserved (→ FIFO queues).
        ack_deadline_seconds: Source acknowledgment deadline (maps to SQS visibility timeout).
    """
    return recommend_messaging_target(
        delivery_pattern=delivery_pattern,
        subscriber_count=subscriber_count,
        ordering_required=ordering_required,
        ack_deadline_seconds=ack_deadline_seconds,
        knowledge=_knowledge,
    )


@mcp.tool()
def normalize_resource(
    source_type: str,
    raw_config: dict,
    resolved_primaries: list[dict] | None = None,
) -> dict:
    """Normalize a source resource to canonical model fields.

    Translates source-native field names and values into the canonical model
    that recommend_* tools consume. Returns extracted fields plus a list of
    fields that require LLM inference.

    For secondary resources with parent dependencies (e.g., node pools),
    pass resolved_primaries to enable parent-aware skip/proceed logic.

    Args:
        source_type: Terraform resource type (e.g., google_sql_database_instance, heroku_addon:heroku-postgresql).
        raw_config: Raw resource configuration dict from the discovery inventory.
        resolved_primaries: Optional list of already-resolved primary resources in this cluster.
            Each entry should have at minimum: {"type": "<source_type>", "aws_service": "<resolved target>"}.
    """
    return _normalize_resource(
        source_type=source_type,
        raw_config=raw_config,
        knowledge=_knowledge,
        resolved_primaries=resolved_primaries,
    )


@mcp.tool()
def lookup_direct_mapping(
    source_type: str,
    condition_context: dict | None = None,
    raw_config: dict | None = None,
) -> dict:
    """Check if a source resource has an unconditional direct AWS mapping.

    Pass 1 fast-path lookup. If hit, returns the AWS target with deterministic
    confidence — no further tools needed for this resource. If miss, proceed
    to normalize_resource → recommend_database/compute.

    Args:
        source_type: Terraform resource type (e.g., google_storage_bucket).
        condition_context: Optional fields for conditional mappings (e.g., {"engine": "sqlserver"}).
        raw_config: Optional raw resource config. If provided, the tool auto-extracts
            condition fields (e.g., database_version → engine for Cloud SQL) so you
            don't need to manually pass condition_context.
    """
    return _lookup_direct_mapping(
        source_type=source_type,
        condition_context=condition_context,
        raw_config=raw_config,
        knowledge=_knowledge,
    )


@mcp.tool()
def validate_design(
    design: dict,
    clusters_source: dict | None = None,
) -> dict:
    """Validate aws-design.json against the output checklist.

    Runs structural assertions: non-empty clusters, required fields on every
    resource, confidence enum, BigQuery→Deferred gate, SQL→correct family,
    no duplicate addresses. Returns pass/fail with specific violations.

    Args:
        design: The aws-design.json content as a dict.
        clusters_source: Optional gcp-resource-clusters.json for cluster_id cross-check.
    """
    return _validate_design(
        design=design,
        clusters_source=clusters_source,
        knowledge=_knowledge,
    )


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
