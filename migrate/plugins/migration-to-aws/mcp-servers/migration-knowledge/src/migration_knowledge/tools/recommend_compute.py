"""recommend_compute_target — deterministic compute service selection + sizing.

Funnel: DISCOVER → CONSTRAIN → RESOLVE → VERIFY → CONFIGURE
Each stage is a self-contained function with clear inputs and outputs.
"""

import logging
from typing import Any

logger = logging.getLogger("migration_tools.recommend_compute")


def _eval_condition(value, op: str, threshold) -> bool:
    """Evaluate a single condition (field op value)."""
    ops = {">": lambda a, b: a > b, ">=": lambda a, b: a >= b,
           "<": lambda a, b: a < b, "<=": lambda a, b: a <= b,
           "==": lambda a, b: a == b, "!=": lambda a, b: a != b,
           "contains": lambda a, b: b in str(a).lower() if a else False}
    return ops.get(op, lambda a, b: False)(value, threshold)


# ─── DISCOVER ─────────────────────────────────────────────────────────────────

def discover(definition: dict) -> tuple[list[str], str]:
    """Given an archetype definition, return all possible candidates and the default.

    Returns:
        (candidates, default_target)
    """
    candidates = list(definition.get("candidates", []))
    default = definition.get("default", "Fargate")
    return candidates, default


# ─── CONSTRAIN ────────────────────────────────────────────────────────────────

def constrain(
    candidates: list[str],
    constraints: list[dict],
    timeout_seconds: int | None,
    vcpu: float,
    memory_gb: float,
    gpu: bool,
    runtime: str | None,
) -> tuple[list[str], set[str], list[str]]:
    """Remove candidates that are physically impossible for this resource.

    Returns:
        (remaining_candidates, excluded_set, rubric_entries)
    """
    fields = {"timeout_seconds": timeout_seconds, "vcpu": vcpu, "memory_gb": memory_gb, "gpu": gpu, "runtime": runtime}
    excluded = set()
    rubric = []

    for entry in constraints:
        # Always-excluded services
        if entry.get("when") == "always" and entry.get("excludes"):
            excluded.add(entry["excludes"])
            rubric.append(f"{entry['id']}: {entry['excludes']} always excluded")
            continue

        # Conditional constraints
        when = entry.get("when", {})
        if not isinstance(when, dict):
            continue

        triggered = False
        field_name = when.get("field")
        if field_name and field_name in fields:
            val = fields[field_name]
            if val is not None:
                triggered = _eval_condition(val, when["op"], when["value"])

        if triggered and entry.get("excludes"):
            excluded.add(entry["excludes"])
            rubric.append(f"constraint: {entry['id']} → exclude {entry['excludes']}")

    remaining = [c for c in candidates if c not in excluded]
    return remaining, excluded, rubric


# ─── RESOLVE ──────────────────────────────────────────────────────────────────

def resolve(
    remaining: list[str],
    excluded: set[str],
    default_target: str,
    resolution_rules: list[dict],
    constraints_for_fallback: list[dict],
    kubernetes_pref: str | None,
    workload_pattern: str | None,
    cost_sensitivity: str | None,
) -> tuple[str, list[dict], bool, list[str]]:
    """From remaining candidates, pick the winner using preferences and signals.

    Priority order: forced override → explicit preference → workload adjustment → default.
    First match wins.

    Returns:
        (winner, alternatives, tie_break_required, rubric_entries)
    """
    target = default_target if default_target in remaining else None
    rubric = []

    # If default was excluded, use the fallback from the constraint that excluded it
    if target is None:
        # Find the constraint that excluded the default and use its fallback
        for entry in constraints_for_fallback:
            if entry.get("excludes") == default_target and entry.get("fallback"):
                fb = entry["fallback"]
                if fb in remaining:
                    target = fb
                    rubric.append(f"default {default_target} excluded → fallback {fb}")
                    break
        if target is None:
            target = remaining[0] if remaining else "Fargate"
            rubric.append(f"default {default_target} excluded → first remaining {target}")
    else:
        rubric.append(f"default → {target}")
    alternatives = []
    tie_break = False

    for rule in resolution_rules:
        rule_type = rule.get("type")
        when = rule.get("when", {})

        # Force: unconditionally select this service
        if rule_type == "force":
            trigger_value = when.get("value") if isinstance(when, dict) else None
            if trigger_value and workload_pattern == trigger_value:
                forced = rule.get("select")
                if forced and forced in remaining:
                    target = forced
                    rubric.append(f"workload={workload_pattern} → force {target}")
                    return target, alternatives, tie_break, rubric

        # Preference: map a preference value to a service
        if rule_type == "preference":
            pref_map = rule.get("map", {})
            pref_value = kubernetes_pref  # currently only k8s pref uses this type
            if pref_value and pref_value in pref_map:
                selected = pref_map[pref_value]
                if selected and selected in remaining:
                    target = selected
                    rubric.append(f"kubernetes_pref={pref_value} → {target}")

        # Adjustment: switch from one service to another based on signal
        if rule_type == "adjustment":
            trigger_value = when.get("value") if isinstance(when, dict) else None
            if trigger_value and workload_pattern == trigger_value:
                if rule.get("if_current") == target and rule.get("switch_to"):
                    switch = rule["switch_to"]
                    if switch in remaining:
                        old = target
                        target = switch
                        rubric.append(f"workload={workload_pattern}: {old} → {target}")

        # Alternative: suggest a competing option (tie-break required)
        if rule_type == "alternative":
            trigger_value = when.get("value") if isinstance(when, dict) else None
            if trigger_value and cost_sensitivity == trigger_value:
                if rule.get("if_current") == target and rule.get("suggest"):
                    alt = rule["suggest"]
                    if alt in remaining:
                        alternatives.append({"aws_service": alt, "reason": rule.get("reason", "")})
                        tie_break = rule.get("tie_break", False)
                        rubric.append(f"cost={cost_sensitivity} → alternative {alt}")

    return target, alternatives, tie_break, rubric


# ─── VERIFY ───────────────────────────────────────────────────────────────────

def verify(
    target: str,
    excluded: set[str],
    constraints: list[dict],
) -> tuple[str, list[str]]:
    """Confirm the resolved target isn't in the excluded set. Fallback if it is.

    Returns:
        (confirmed_target, rubric_entries)
    """
    rubric = []
    if target not in excluded:
        return target, rubric

    # Find a fallback from the constraint that excluded it
    for entry in constraints:
        if entry.get("excludes") == target and entry.get("fallback"):
            fallback = entry["fallback"]
            if fallback not in excluded:
                rubric.append(f"verify: {target} excluded → fallback {fallback}")
                return fallback, rubric

    rubric.append(f"verify: {target} excluded, no valid fallback found")
    return target, rubric


# ─── CONFIGURE ────────────────────────────────────────────────────────────────

def configure(
    target: str,
    vcpu: float,
    memory_gb: float,
    timeout_seconds: int | None,
    gpu: bool,
    sizing_data: dict,
) -> tuple[dict, str, list[str]]:
    """Produce the concrete AWS config (sizing/topology) for the chosen service.

    Returns:
        (aws_config, final_target, rubric_entries)
        final_target may differ from input if sizing fails (e.g., Fargate overflow → EC2).
    """
    aws_config = {"region": "us-east-1"}
    rubric = []

    if target == "Fargate":
        combos = sizing_data.get("fargate", {}).get("valid_combos", [])
        snapped = _snap_to_fargate(vcpu, memory_gb, combos)
        if snapped is None:
            # Exceeded Fargate limits — fall to EC2
            target = "EC2"
            if gpu:
                entries = sizing_data.get("ec2", {}).get("gpu_instance_mapping", [])
                aws_config["instance_type"] = _find_gpu_instance(vcpu, memory_gb, entries)
                rubric.append(f"Fargate overflow + GPU → EC2 {aws_config['instance_type']}")
            else:
                entries = sizing_data.get("ec2", {}).get("instance_mapping", [])
                aws_config["instance_type"] = _find_ec2_instance(vcpu, memory_gb, entries)
                rubric.append(f"Fargate overflow → EC2 {aws_config['instance_type']}")
        else:
            aws_config["cpu"] = snapped["cpu"]
            aws_config["memory_gb"] = snapped["memory_gb"]
            rubric.append(f"Fargate: {snapped['cpu']} vCPU / {snapped['memory_gb']} GB")

    elif target == "EC2":
        if gpu:
            entries = sizing_data.get("ec2", {}).get("gpu_instance_mapping", [])
            aws_config["instance_type"] = _find_gpu_instance(vcpu, memory_gb, entries)
            rubric.append(f"EC2 GPU: {aws_config['instance_type']}")
        else:
            entries = sizing_data.get("ec2", {}).get("instance_mapping", [])
            aws_config["instance_type"] = _find_ec2_instance(vcpu, memory_gb, entries)
            rubric.append(f"EC2: {aws_config['instance_type']}")

    elif target == "Lambda":
        lcfg = sizing_data.get("lambda", {})
        mem = min(max(int(memory_gb * 1024), lcfg.get("memory_min_mb", 128)), lcfg.get("memory_max_mb", 10240))
        aws_config["memory_mb"] = mem
        aws_config["timeout_seconds"] = min(timeout_seconds or 60, lcfg.get("timeout_max_seconds", 900))
        rubric.append(f"Lambda: {mem}MB / {aws_config['timeout_seconds']}s")

    elif target == "EKS":
        aws_config["managed_node_group"] = True
        aws_config["notes"] = "Node pool sizing deferred to Generate phase"
        rubric.append("EKS: sizing deferred")

    return aws_config, target, rubric


# ─── Sizing helpers (used by CONFIGURE) ───────────────────────────────────────

def _snap_to_fargate(vcpu: float, memory_gb: float, combos: list[dict]) -> dict | None:
    """Snap to nearest valid Fargate cpu/memory combo (round up)."""
    for combo in combos:
        if combo["cpu"] >= vcpu and combo["memory_max_gb"] >= memory_gb:
            return {"cpu": combo["cpu"], "memory_gb": max(memory_gb, combo["memory_min_gb"])}
    return None


def _find_ec2_instance(vcpu: float, memory_gb: float, entries: list[dict]) -> str:
    """Find smallest EC2 instance that fits."""
    for entry in entries:
        if entry["vcpu_max"] >= vcpu and entry["memory_max_gb"] >= memory_gb:
            return entry["instance_type"]
    return entries[-1]["instance_type"] if entries else "m5.xlarge"


def _find_gpu_instance(vcpu: float, memory_gb: float, entries: list[dict]) -> str:
    """Find smallest GPU instance that fits by vCPU and memory."""
    for entry in entries:
        if entry["vcpu_max"] >= vcpu and entry["memory_max_gb"] >= memory_gb:
            return entry["instance_type"]
    return entries[-1]["instance_type"] if entries else "p3.8xlarge"


# ─── Main entry point ─────────────────────────────────────────────────────────

def recommend_compute_target(
    service_type: str,
    timeout_seconds: int | None = None,
    vcpu: float = 0.25,
    memory_gb: float = 0.5,
    gpu: bool = False,
    runtime: str | None = None,
    workload_pattern: str | None = None,
    kubernetes_pref: str | None = None,
    cost_sensitivity: str | None = None,
    knowledge: dict[str, Any] = None,
) -> dict:
    """Deterministic compute target recommendation.

    Funnel: DISCOVER → CONSTRAIN → RESOLVE → VERIFY → CONFIGURE
    """
    logger.info(">>> recommend_compute_target called")
    logger.info("  input: service_type=%s, timeout=%s, vcpu=%s, memory_gb=%s, gpu=%s, runtime=%s, workload_pattern=%s, k8s_pref=%s, cost_sensitivity=%s",
                service_type, timeout_seconds, vcpu, memory_gb, gpu, runtime, workload_pattern, kubernetes_pref, cost_sensitivity)

    # Load archetype knowledge
    archetype = service_type
    valid_types = {"container", "function", "vm"}
    # Alias common alternative names
    aliases = {"kubernetes": "container", "app-engine": "container"}
    archetype = aliases.get(archetype, archetype)
    if archetype not in valid_types:
        return {"error": f"Unknown service_type: '{archetype}'. Valid: {list(valid_types)}"}

    arch_base = f"universal/archetypes/{archetype}"
    definition = knowledge.get(f"{arch_base}/definition", {})
    constraints_data = knowledge.get(f"{arch_base}/constraints", {}).get("entries", [])
    resolution_rules = knowledge.get(f"{arch_base}/resolution", {}).get("priority_order", [])
    sizing_data = knowledge.get(f"{arch_base}/sizing", {})

    rubric_applied = []

    # ── DISCOVER ──────────────────────────────────────────────────────────────
    candidates, default_target = discover(definition)
    logger.info("  DISCOVER: candidates=%s, default=%s", candidates, default_target)

    # ── CONSTRAIN ─────────────────────────────────────────────────────────────
    remaining, excluded, constrain_rubric = constrain(
        candidates, constraints_data, timeout_seconds, vcpu, memory_gb, gpu, runtime
    )
    rubric_applied.extend(constrain_rubric)
    logger.info("  CONSTRAIN: remaining=%s, excluded=%s", remaining, excluded)

    # ── RESOLVE ───────────────────────────────────────────────────────────────
    target, alternatives, tie_break_required, resolve_rubric = resolve(
        remaining, excluded, default_target, resolution_rules, constraints_data,
        kubernetes_pref, workload_pattern, cost_sensitivity
    )
    rubric_applied.extend(resolve_rubric)
    logger.info("  RESOLVE: target=%s, alternatives=%s", target, [a["aws_service"] for a in alternatives])

    # ── VERIFY ────────────────────────────────────────────────────────────────
    target, verify_rubric = verify(target, excluded, constraints_data)
    rubric_applied.extend(verify_rubric)
    logger.info("  VERIFY: target=%s", target)

    # ── CONFIGURE ─────────────────────────────────────────────────────────────
    aws_config, target, config_rubric = configure(target, vcpu, memory_gb, timeout_seconds, gpu, sizing_data)
    rubric_applied.extend(config_rubric)
    logger.info("  CONFIGURE: %s → %s", target, aws_config)

    # ── Result ────────────────────────────────────────────────────────────────
    result = {
        "aws_service": target,
        "aws_config": aws_config,
        "confidence": "inferred",
        "human_expertise_required": False,
        "rubric_applied": rubric_applied,
        "alternatives": alternatives,
        "tie_break_required": tie_break_required,
        "warnings": [],
    }
    logger.info("<<< returning: aws_service=%s", target)
    return result
