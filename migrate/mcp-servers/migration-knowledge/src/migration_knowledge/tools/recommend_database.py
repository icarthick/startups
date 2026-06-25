"""recommend_database_target — deterministic database service selection + sizing.

Funnel: DISCOVER → CONSTRAIN → RESOLVE → VERIFY → CONFIGURE
Each stage is a self-contained function with clear inputs and outputs.
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


# ─── DISCOVER ─────────────────────────────────────────────────────────────────

def discover(definition: dict) -> tuple[list[str], str]:
    """Given the relational-db archetype definition, return candidates and default.

    Returns:
        (candidates, default_target)  e.g. (["RDS", "Aurora"], "RDS")
    """
    candidates = list(definition.get("candidates", ["RDS", "Aurora"]))
    default = definition.get("default", "RDS")
    return candidates, default


# ─── CONSTRAIN ────────────────────────────────────────────────────────────────

def constrain(
    candidates: list[str],
    constraints: list[dict],
    engine: str,
) -> tuple[list[str], set[str], list[str], dict | None]:
    """Remove candidates that are impossible for this engine.

    Also detects engines that need user confirmation (Oracle, MariaDB).

    Returns:
        (remaining_candidates, excluded_set, rubric_entries, needs_clarification_response_or_None)
    """
    excluded = set()
    rubric = []

    for entry in constraints:
        when = entry.get("when", {})
        if not isinstance(when, dict):
            continue

        if when.get("field") == "engine" and when.get("value") == engine:
            if entry.get("needs_clarification"):
                # Engine requires user decision before proceeding
                response = {
                    "needs_clarification": entry["needs_clarification"],
                    "engine": engine,
                    "reason": entry.get("reason", ""),
                }
                if entry.get("escape_path"):
                    response["escape_path"] = entry["escape_path"]
                if entry.get("alternative_engine"):
                    response["alternative_engine"] = entry["alternative_engine"]
                return [], set(), rubric, response
            if entry.get("excludes") and entry["excludes"] != "_all":
                excluded.add(entry["excludes"])
                rubric.append(f"constraint: {entry['id']} → exclude {entry['excludes']}")

    remaining = [c for c in candidates if c not in excluded]
    return remaining, excluded, rubric, None


# ─── RESOLVE ──────────────────────────────────────────────────────────────────

def resolve(
    remaining: list[str],
    availability: str | None,
    resolution: dict,
) -> tuple[str, bool, dict | None, list[str]]:
    """Select the winning family (RDS or Aurora) based on availability preference (Q6).

    Returns:
        (family, multi_az, topology_or_None, rubric_entries)
        Returns a needs_clarification dict instead of family if availability is None.
    """
    avail_matrix = resolution.get("availability_matrix", {}).get("map", {})
    absent_behavior = resolution.get("availability_matrix", {}).get("absent_behavior", "needs_clarification")

    if availability is None:
        return None, False, {"needs_clarification": "availability", "reason": "Cannot determine RDS vs Aurora without availability requirement (Q6). Never infers Aurora."}, []

    if availability not in avail_matrix:
        return None, False, {"error": f"Unknown availability: '{availability}'. Valid: {list(avail_matrix.keys())}"}, []

    result = avail_matrix[availability]
    family = result["select"]
    multi_az = result.get("multi_az", False)
    topology = result.get("topology")
    rubric = [f"availability={availability} → {family}"]

    # Verify family is in remaining candidates
    if family not in remaining:
        return None, False, {"error": f"Engine does not support '{family}'. Available: {remaining}"}, rubric

    return family, multi_az, topology, rubric


# ─── VERIFY ───────────────────────────────────────────────────────────────────

def verify(
    family: str,
    engine: str,
    engine_entry: dict,
) -> tuple[bool, list[str], dict | None]:
    """Confirm the engine supports the resolved family.

    Returns:
        (valid, rubric_entries, error_response_or_None)
    """
    if family not in engine_entry.get("families", {}):
        return False, [], {
            "error": f"Engine '{engine}' does not support family '{family}'.",
            "valid_families": list(engine_entry.get("families", {}).keys()),
        }
    return True, [f"verify: {engine} × {family} → valid"], None


# ─── CONFIGURE ────────────────────────────────────────────────────────────────

def configure(
    family: str,
    engine_entry: dict,
    family_config: dict,
    resolution: dict,
    size_class: str,
    io_workload: str,
    traffic: str,
    data_size_gb: float | None,
    engine: str,
) -> tuple[dict, str, str, list[str]]:
    """Produce concrete AWS config: instance class (or ACU), storage, replicas, migration tool.

    Returns:
        (aws_config, aws_service_name, migration_tool, rubric_entries)
    """
    rubric = []

    # Traffic scaling (family-aware)
    traffic_rules = resolution.get("traffic_scaling", {}).get("by_family", {}).get(family, {})
    traffic_result = traffic_rules.get(traffic, {"add_replica": False, "sizing_hint": "standard"})
    rubric.append(f"traffic={traffic} → {traffic_result.get('sizing_hint', 'standard')}")

    # Sizing: instance class or Serverless v2 ACU
    use_serverless = traffic_result.get("serverless_v2", False)

    if use_serverless and family_config.get("supports_serverless_v2"):
        acu_ranges = family_config.get("serverless_v2_acu", {})
        acu = acu_ranges.get(size_class, {"min": 0.5, "max": 2})
        instance_class = None
        rubric.append(f"serverless_v2, size_class={size_class} → ACU {acu['min']}-{acu['max']}")
    else:
        instance_classes = family_config.get("instance_classes", {})
        instance_class = instance_classes.get(size_class, "db.t4g.micro")
        acu = None
        rubric.append(f"size_class={size_class} → {instance_class}")

    # Storage type (family-aware)
    storage_rules = resolution.get("storage_rules", {}).get("by_family", {}).get(family, {})
    storage_type = storage_rules.get(io_workload, "gp3")
    rubric.append(f"io_workload={io_workload} → {storage_type}")

    # Replicas
    add_replica = traffic_result.get("add_replica", False)
    replica_type = traffic_result.get("replica_type")
    if add_replica:
        rubric.append(f"traffic={traffic} → add {replica_type}")

    # Migration tooling
    from migration_knowledge.tools.recommend_database import _bucket_data_size
    sizing_data = family_config  # not ideal but tooling is in the parent sizing file
    # Access migration_tooling from the engine_entry's parent (sizing.json root)
    # We pass it in via a workaround — see main function
    size_bucket = _bucket_data_size(data_size_gb)

    # Compose service name
    aws_service = f"{family} {engine_entry['aws_service_suffix']}"

    # Build aws_config
    aws_config = {
        "instance_class": instance_class,
        "multi_az": None,  # set by caller from resolve output
        "storage_type": storage_type,
    }
    if acu:
        aws_config["min_acu"] = acu["min"]
        aws_config["max_acu"] = acu["max"]
    if add_replica:
        aws_config["read_replica"] = True
        aws_config["replica_type"] = replica_type

    return aws_config, aws_service, rubric, size_bucket


# ─── Main entry point ─────────────────────────────────────────────────────────

def recommend_database_target(
    engine: str,
    availability: str | None,
    size_class: str = "micro",
    io_workload: str = "low",
    traffic: str = "steady",
    data_size_gb: float | None = None,
    knowledge: dict[str, Any] = None,
) -> dict:
    """Deterministic database target recommendation.

    Funnel: DISCOVER → CONSTRAIN → RESOLVE → VERIFY → CONFIGURE
    """
    logger.info(">>> recommend_database_target called")
    logger.info("  input: engine=%s, availability=%s, size_class=%s, io_workload=%s, traffic=%s, data_size_gb=%s",
                engine, availability, size_class, io_workload, traffic, data_size_gb)

    # Load archetype knowledge
    arch_base = "universal/archetypes/relational-db"
    definition = knowledge.get(f"{arch_base}/definition", {})
    constraints_data = knowledge.get(f"{arch_base}/constraints", {}).get("entries", [])
    resolution = knowledge.get(f"{arch_base}/resolution", {})
    sizing_data = knowledge.get(f"{arch_base}/sizing", {})

    rubric_applied = []

    # ── DISCOVER ──────────────────────────────────────────────────────────────
    candidates, default_target = discover(definition)
    logger.info("  DISCOVER: candidates=%s, default=%s", candidates, default_target)

    # ── CONSTRAIN ─────────────────────────────────────────────────────────────
    remaining, excluded, constrain_rubric, clarification = constrain(candidates, constraints_data, engine)
    rubric_applied.extend(constrain_rubric)
    if clarification:
        logger.info("  CONSTRAIN: needs clarification for engine=%s", engine)
        return clarification
    logger.info("  CONSTRAIN: remaining=%s, excluded=%s", remaining, excluded)

    # ── RESOLVE ───────────────────────────────────────────────────────────────
    family, multi_az, resolve_result, resolve_rubric = resolve(remaining, availability, resolution)
    rubric_applied.extend(resolve_rubric)
    if family is None:
        # resolve_result is either needs_clarification or error
        logger.info("  RESOLVE: %s", resolve_result)
        return resolve_result
    logger.info("  RESOLVE: family=%s, multi_az=%s", family, multi_az)

    # ── VERIFY ────────────────────────────────────────────────────────────────
    engine_config = sizing_data.get("engine_configuration", {})
    engine_entry = engine_config.get(engine, {})
    valid, verify_rubric, verify_error = verify(family, engine, engine_entry)
    rubric_applied.extend(verify_rubric)
    if not valid:
        logger.error("  VERIFY: failed — %s", verify_error)
        return verify_error
    family_config = engine_entry["families"][family]
    logger.info("  VERIFY: %s × %s → valid", engine, family)

    # ── CONFIGURE ─────────────────────────────────────────────────────────────
    aws_config, aws_service, config_rubric, size_bucket = configure(
        family, engine_entry, family_config, resolution,
        size_class, io_workload, traffic, data_size_gb, engine
    )
    aws_config["multi_az"] = multi_az
    if isinstance(resolve_result, str):
        aws_config["topology"] = resolve_result
    rubric_applied.extend(config_rubric)

    # Migration tooling (from sizing.json root)
    tooling = sizing_data.get("migration_tooling", {}).get("map", {})
    tooling_result = tooling.get(size_bucket, tooling.get("unknown", {}))
    tool_key = "tool" if engine != "mysql" else "mysql_tool"
    migration_tool = tooling_result.get(tool_key, "pgcopydb")
    rubric_applied.append(f"data_size={size_bucket} → {migration_tool}")

    logger.info("  CONFIGURE: %s, instance=%s, storage=%s, tool=%s",
                aws_service, aws_config.get("instance_class"), aws_config.get("storage_type"), migration_tool)

    # ── Result ────────────────────────────────────────────────────────────────
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
    logger.info("<<< returning: aws_service=%s", aws_service)
    return result
