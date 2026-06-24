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

    # --- Step 1: Determine family from availability ---
    logger.debug("Step 1: looking up availability matrix")
    avail_matrix = knowledge["universal/db/availability-matrix"]["matrix"]

    if availability is None:
        logger.info("  → needs_clarification: availability is None")
        return {"needs_clarification": "availability", "reason": "Cannot determine RDS vs Aurora without availability requirement (Q6). Never infers Aurora."}

    if availability not in avail_matrix:
        logger.error("  → error: unknown availability '%s'", availability)
        return {"error": f"Unknown availability value: '{availability}'. Valid: {list(avail_matrix.keys())}"}

    family_result = avail_matrix[availability]
    family = family_result["family"]
    multi_az = family_result.get("multi_az", False)
    topology = family_result.get("topology")
    rubric_applied.append(f"availability={availability} → {family}")
    logger.info("  Step 1 result: family=%s, multi_az=%s, topology=%s", family, multi_az, topology)

    # --- Step 2: Navigate engine configuration ---
    logger.debug("Step 2: navigating engine configuration")
    engine_config = knowledge["universal/db/engine-configuration"]["entries"]

    if engine not in engine_config:
        logger.error("  → error: unknown engine '%s'", engine)
        return {"error": f"Unknown engine: '{engine}'. Valid: {list(engine_config.keys())}"}

    engine_entry = engine_config[engine]

    # Check if engine needs user confirmation (e.g. Oracle escape path, MariaDB choice)
    if engine_entry.get("needs_user_confirmation"):
        logger.info("  → needs_clarification: engine '%s' requires user confirmation", engine)
        return {
            "needs_clarification": "engine_choice",
            "engine": engine,
            "reason": engine_entry["confirmation_reason"],
            "alternative_engine": engine_entry.get("alternative_engine"),
            "escape_path": engine_entry.get("escape_path"),
        }

    # Validate family support
    if family not in engine_entry["families"]:
        logger.error("  → error: engine '%s' does not support family '%s'", engine, family)
        return {
            "error": f"Engine '{engine}' does not support family '{family}'.",
            "valid_families": list(engine_entry["families"].keys()),
            "suggestion": f"Change availability to one that maps to {list(engine_entry['families'].keys())}",
        }

    family_config = engine_entry["families"][family]
    logger.info("  Step 2: engine=%s, family=%s → config loaded", engine, family)

    # --- Traffic scaling ---
    if traffic not in family_config["traffic_scaling"]:
        logger.error("  → error: unknown traffic '%s'", traffic)
        return {"error": f"Unknown traffic value: '{traffic}'. Valid: {list(family_config['traffic_scaling'].keys())}"}

    traffic_result = family_config["traffic_scaling"][traffic]
    rubric_applied.append(f"traffic={traffic} → {traffic_result.get('sizing_hint', 'standard')}")
    logger.info("  Traffic scaling: traffic=%s → %s", traffic, traffic_result)

    # --- Sizing (instance class or Serverless v2 ACU) ---
    use_serverless = traffic_result.get("serverless_v2", False)

    if use_serverless and family_config.get("supports_serverless_v2"):
        acu_ranges = family_config["serverless_v2"]["acu_ranges"]
        if size_class not in acu_ranges:
            logger.error("  → error: unknown size_class '%s' for serverless", size_class)
            return {"error": f"Unknown size_class: '{size_class}'. Valid: {list(acu_ranges.keys())}"}
        acu = acu_ranges[size_class]
        instance_class = None
        rubric_applied.append(f"serverless_v2=true, size_class={size_class} → ACU {acu['min']}-{acu['max']}")
        logger.info("  Sizing: serverless_v2, size_class=%s → ACU %s-%s", size_class, acu['min'], acu['max'])
    else:
        if size_class not in family_config["instance_classes"]:
            logger.error("  → error: unknown size_class '%s'", size_class)
            return {"error": f"Unknown size_class: '{size_class}'. Valid: {list(family_config['instance_classes'].keys())}"}
        instance_class = family_config["instance_classes"][size_class]
        acu = None
        rubric_applied.append(f"size_class={size_class} → {instance_class}")
        logger.info("  Sizing: size_class=%s → instance_class=%s", size_class, instance_class)

    # --- Storage type ---
    if io_workload not in family_config["storage_types"]:
        logger.error("  → error: unknown io_workload '%s'", io_workload)
        return {"error": f"Unknown io_workload: '{io_workload}'. Valid: {list(family_config['storage_types'].keys())}"}

    storage_type = family_config["storage_types"][io_workload]
    rubric_applied.append(f"io_workload={io_workload} → {storage_type}")
    logger.info("  Storage: io_workload=%s → %s", io_workload, storage_type)

    # --- Replicas ---
    add_replica = traffic_result.get("add_replica", False)
    replica_type = traffic_result.get("replica_type")
    if add_replica:
        rubric_applied.append(f"traffic={traffic} → add {replica_type}")
        logger.info("  Replicas: add_replica=true, type=%s", replica_type)
    else:
        logger.info("  Replicas: none")

    # --- Migration tooling ---
    tooling_data = knowledge["universal/db-migration-tooling"]["matrix"]  # stays at flat path (not engine/family dependent)
    size_bucket = _bucket_data_size(data_size_gb)
    tooling_result = tooling_data.get(size_bucket, tooling_data["unknown"])
    tool_key = "tool" if engine != "mysql" else "mysql_tool"
    migration_tool = tooling_result[tool_key]
    rubric_applied.append(f"data_size={size_bucket} → {migration_tool}")
    logger.info("  Migration tooling: data_size_gb=%s → bucket=%s → %s", data_size_gb, size_bucket, migration_tool)

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
