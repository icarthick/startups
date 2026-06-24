"""recommend_networking_target — deterministic load balancer selection.

Funnel: DISCOVER → CONSTRAIN → RESOLVE → VERIFY → CONFIGURE
"""

import logging
from typing import Any

logger = logging.getLogger("migration_tools.recommend_networking")


def _eval_condition(value, op: str, threshold) -> bool:
    ops = {">": lambda a, b: a > b, "==": lambda a, b: a == b,
           "!=": lambda a, b: a != b, "contains": lambda a, b: b in str(a).lower() if a else False}
    return ops.get(op, lambda a, b: False)(value, threshold)


def discover(definition: dict) -> tuple[list[str], str]:
    return list(definition.get("candidates", [])), definition.get("default", "ALB")


def constrain(candidates: list[str], constraints: list[dict], protocol: str | None) -> tuple[list[str], set[str], list[str]]:
    fields = {"protocol": protocol}
    excluded = set()
    rubric = []
    for entry in constraints:
        when = entry.get("when", {})
        if not isinstance(when, dict):
            continue
        field_name = when.get("field")
        if field_name and field_name in fields:
            val = fields[field_name]
            if val is not None and _eval_condition(val, when["op"], when["value"]):
                excluded.add(entry["excludes"])
                rubric.append(f"constraint: {entry['id']} → exclude {entry['excludes']}")
    remaining = [c for c in candidates if c not in excluded]
    return remaining, excluded, rubric


def resolve(
    remaining: list[str], excluded: set[str], default_target: str,
    resolution_rules: list[dict], constraints_data: list[dict],
    protocol: str | None, performance_priority: str | None,
) -> tuple[str, list[dict], bool, list[str]]:
    target = default_target if default_target in remaining else None
    rubric = []

    if target is None:
        for entry in constraints_data:
            if entry.get("excludes") == default_target and entry.get("fallback"):
                fb = entry["fallback"]
                if fb in remaining:
                    target = fb
                    rubric.append(f"default {default_target} excluded → fallback {fb}")
                    break
        if target is None:
            target = remaining[0] if remaining else "ALB"

    for rule in resolution_rules:
        rule_type = rule.get("type")
        when = rule.get("when", {})
        trigger_value = when.get("value") if isinstance(when, dict) else None
        field = when.get("field") if isinstance(when, dict) else None

        if rule_type == "force" and trigger_value:
            # Match protocol field
            if field == "protocol" and protocol == trigger_value:
                forced = rule.get("select")
                if forced and forced in remaining:
                    target = forced
                    rubric.append(f"protocol={protocol} → force {target}")
                    return target, [], False, rubric
            # Match subscriber_count style (numeric >)
            if field == "subscriber_count":
                pass  # not applicable for networking

        if rule_type == "adjustment" and trigger_value:
            if field == "performance_priority" and performance_priority == trigger_value:
                if rule.get("if_current") == target and rule.get("switch_to"):
                    switch = rule["switch_to"]
                    if switch in remaining:
                        old = target
                        target = switch
                        rubric.append(f"performance={performance_priority}: {old} → {target}")

    if not rubric:
        rubric.append(f"default → {target}")
    return target, [], False, rubric


def verify(target: str, excluded: set[str], constraints: list[dict]) -> tuple[str, list[str]]:
    if target not in excluded:
        return target, []
    for entry in constraints:
        if entry.get("excludes") == target and entry.get("fallback"):
            fb = entry["fallback"]
            if fb not in excluded:
                return fb, [f"verify: {target} excluded → fallback {fb}"]
    return target, [f"verify: {target} excluded, no valid fallback"]


def configure(target: str, scheme: str | None, port_range: str | None, sizing_data: dict) -> tuple[dict, list[str]]:
    rubric = []
    service_key = "alb" if target == "ALB" else "nlb"
    svc = sizing_data.get(service_key, {})
    scheme_map = svc.get("scheme_map", {})
    aws_config = {
        "scheme": scheme_map.get(scheme, svc.get("default_scheme", "internet-facing")),
        "region": "us-east-1",
    }
    if port_range:
        aws_config["port"] = port_range
    if target == "NLB" and svc.get("cross_zone_default"):
        aws_config["cross_zone_load_balancing"] = True
    rubric.append(f"{target}: scheme={aws_config['scheme']}")
    return aws_config, rubric


def recommend_networking_target(
    protocol: str | None = None,
    scheme: str | None = None,
    port_range: str | None = None,
    performance_priority: str | None = None,
    knowledge: dict[str, Any] = None,
) -> dict:
    """Deterministic load balancer recommendation.

    Funnel: DISCOVER → CONSTRAIN → RESOLVE → VERIFY → CONFIGURE
    """
    logger.info(">>> recommend_networking_target: protocol=%s, scheme=%s", protocol, scheme)

    arch_base = "universal/archetypes/load-balancer"
    definition = knowledge.get(f"{arch_base}/definition", {})
    constraints_data = knowledge.get(f"{arch_base}/constraints", {}).get("entries", [])
    resolution_rules = knowledge.get(f"{arch_base}/resolution", {}).get("priority_order", [])
    sizing_data = knowledge.get(f"{arch_base}/sizing", {})

    rubric_applied = []

    candidates, default_target = discover(definition)
    remaining, excluded, constrain_rubric = constrain(candidates, constraints_data, protocol)
    rubric_applied.extend(constrain_rubric)

    target, alternatives, tie_break, resolve_rubric = resolve(
        remaining, excluded, default_target, resolution_rules, constraints_data,
        protocol, performance_priority,
    )
    rubric_applied.extend(resolve_rubric)

    target, verify_rubric = verify(target, excluded, constraints_data)
    rubric_applied.extend(verify_rubric)

    aws_config, config_rubric = configure(target, scheme, port_range, sizing_data)
    rubric_applied.extend(config_rubric)

    return {
        "aws_service": target,
        "aws_config": aws_config,
        "confidence": "inferred",
        "human_expertise_required": False,
        "rubric_applied": rubric_applied,
        "alternatives": alternatives,
        "tie_break_required": tie_break,
        "warnings": [],
    }
