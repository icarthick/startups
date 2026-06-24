"""recommend_database_target — the first map_* decide tool.

Takes canonical DB inputs, navigates availability-matrix + engine-configuration,
returns a complete AWS database recommendation.
"""

import logging
from typing import Any

logger = logging.getLogger("migration_tools.recommend_database")


def _bucket_data_size(data_size_gb: float | None) -> str:
    if data_size_gb is None:
        return "unknown"
    if data_size_gb < 10:
        return "<10"
    if data_size_gb <= 500:
        return "10-500"
    return ">500"


def recommend_database_target(
    engine: str,
    availability: str | None,
    size_class: str = "micro",
    io_workload: str = "low",
    traffic: str = "steady",
    data_size_gb: float | None = None,
    knowledge: dict[str, Any] = None,
) -> dict:
    """Deterministic database target recommendation."""
    logger.info(">>> recommend_database_target called")
    logger.info("  input: engine=%s, availability=%s, size_class=%s, io_workload=%s, traffic=%s, data_size_gb=%s",
                engine, availability, size_class, io_workload, traffic, data_size_gb)

    rubric_applied = []

    # ── Load archetype knowledge ──────────────────────────────────────────────
    arch_base = "universal/archetypes/relational-db"
    resolution = knowledge[f"{arch_base}/resolution"]
    sizing_data = knowledge[f"{arch_base}/sizing"]

    # ── 1. CONSTRAIN — engine validation ──────────────────────────────────────
    logger.debug("CONSTRAIN: checking engine validity")
    avail_matrix = resolution["availability_matrix"]["map"]

    if availability is None:
        logger.info("  → needs_clarification: availability is None")
        return {"needs_clarification": "availability", "reason": "Cannot determine RDS vs Aurora without availability requirement (Q6). Never infers Aurora."}

    if availability not in avail_matrix:
        logger.error("  → error: unknown availability '%s'", availability)
        return {"error": f"Unknown availability value: '{availability}'. Valid: {list(avail_matrix.keys())}"}

    # ── 2. DISCOVER + DEFAULT — family from availability ──────────────────────
    family_result = avail_matrix[availability]
    family = family_result["select"]
    multi_az = family_result.get("multi_az", False)
    topology = family_result.get("topology")
    rubric_applied.append(f"availability={availability} → {family}")
    logger.info("  DISCOVER: family=%s, multi_az=%s, topology=%s", family, multi_az, topology)

    # ── 3. RESOLVE — engine configuration ─────────────────────────────────────
    logger.debug("RESOLVE: navigating engine configuration")
    engine_config = sizing_data["engine_configuration"]

    if engine not in engine_config:
        logger.error("  → error: unknown engine '%s'", engine)
        return {"error": f"Unknown engine: '{engine}'. Valid: {list(engine_config.keys())}"}

    engine_entry = engine_config[engine]

    # Check if engine needs user confirmation
    if engine_entry.get("needs_user_confirmation"):
        logger.info("  → needs_clarification: engine '%s' requires user confirmation", engine)
        return {
            "needs_clarification": "engine_choice",
            "engine": engine,
            "reason": engine_entry.get("confirmation_reason", "Engine requires user confirmation"),
            "alternative_engine": engine_entry.get("alternative_engine"),
            "escape_path": engine_entry.get("escape_path"),
        }

    # Validate family support
    if family not in engine_entry.get("families", {}):
        logger.error("  → error: engine '%s' does not support family '%s'", engine, family)
        return {
            "error": f"Engine '{engine}' does not support family '{family}'.",
            "valid_families": list(engine_entry.get("families", {}).keys()),
            "suggestion": f"Change availability to one that maps to {list(engine_entry.get('families', {}).keys())}",
        }

    family_config = engine_entry["families"][family]
    logger.info("  RESOLVE: engine=%s, family=%s → config loaded", engine, family)

    # ── Traffic scaling ───────────────────────────────────────────────────────
    traffic_rules = resolution.get("traffic_scaling", {}).get("by_family", {}).get(family, {})
    traffic_result = traffic_rules.get(traffic, {"add_replica": False, "sizing_hint": "standard"})
    rubric_applied.append(f"traffic={traffic} → {traffic_result.get('sizing_hint', 'standard')}")
    logger.info("  Traffic scaling: %s", traffic_result)

    # ── 4. VERIFY ─────────────────────────────────────────────────────────────
    # (engine × family already validated above)

    # ── 5. CONFIGURE — sizing ─────────────────────────────────────────────────
    use_serverless = traffic_result.get("serverless_v2", False)

    if use_serverless and family_config.get("supports_serverless_v2"):
        acu_ranges = family_config.get("serverless_v2_acu", {})
        acu = acu_ranges.get(size_class, {"min": 0.5, "max": 2})
        instance_class = None
        rubric_applied.append(f"serverless_v2, size_class={size_class} → ACU {acu['min']}-{acu['max']}")
        logger.info("  CONFIGURE: serverless_v2, ACU %s-%s", acu['min'], acu['max'])
    else:
        instance_classes = family_config.get("instance_classes", {})
        instance_class = instance_classes.get(size_class, "db.t4g.micro")
        acu = None
        rubric_applied.append(f"size_class={size_class} → {instance_class}")
        logger.info("  CONFIGURE: instance_class=%s", instance_class)

    # Storage type
    storage_rules = resolution.get("storage_rules", {}).get("by_family", {}).get(family, {})
    storage_type = storage_rules.get(io_workload, "gp3")
    rubric_applied.append(f"io_workload={io_workload} → {storage_type}")

    # Replicas
    add_replica = traffic_result.get("add_replica", False)
    replica_type = traffic_result.get("replica_type")
    if add_replica:
        rubric_applied.append(f"traffic={traffic} → add {replica_type}")

    # Migration tooling
    tooling = sizing_data.get("migration_tooling", {}).get("map", {})
    size_bucket = _bucket_data_size(data_size_gb)
    tooling_result = tooling.get(size_bucket, tooling.get("unknown", {}))
    tool_key = "tool" if engine != "mysql" else "mysql_tool"
    migration_tool = tooling_result.get(tool_key, "pgcopydb")
    rubric_applied.append(f"data_size={size_bucket} → {migration_tool}")
    logger.info("  CONFIGURE: migration_tool=%s", migration_tool)

    # --- Compose service name ---
    aws_service = f"{family} {engine_entry['aws_service_suffix']}"
    logger.info("  Composed: aws_service=%s", aws_service)

    # --- Assemble output ---
    aws_config = {
        "instance_class": instance_class,
        "multi_az": multi_az,
        "storage_type": storage_type,
    }

    if topology:
        aws_config["topology"] = topology

    if acu:
        aws_config["min_acu"] = acu["min"]
        aws_config["max_acu"] = acu["max"]

    if add_replica:
        aws_config["read_replica"] = True
        aws_config["replica_type"] = replica_type

    result = {
        "aws_service": aws_service,
        "aws_config": aws_config,
        "migration_tool": migration_tool,
        "confidence": "inferred",
        "human_expertise_required": False,
        "rubric_applied": rubric_applied,
        "alternatives": [],
        "tie_break_required": False,
        "warnings": [],
    }

    logger.info("<<< recommend_database_target returning: aws_service=%s, instance_class=%s, storage=%s",
                aws_service, instance_class or f"ACU {acu}", storage_type)
    return result
