"""recommend_messaging_target — deterministic message broker selection.

Funnel: DISCOVER → CONSTRAIN → RESOLVE → VERIFY → CONFIGURE
"""

import logging
from typing import Any

logger = logging.getLogger("migration_tools.recommend_messaging")


def _eval_condition(value, op: str, threshold) -> bool:
    ops = {">": lambda a, b: a > b, "==": lambda a, b: a == b,
           "!=": lambda a, b: a != b}
    return ops.get(op, lambda a, b: False)(value, threshold)


def discover(definition: dict) -> tuple[list[str], str]:
    return list(definition.get("candidates", [])), definition.get("default", "SQS")


def constrain(candidates: list[str], constraints: list[dict], subscriber_count: int | None) -> tuple[list[str], set[str], list[str]]:
    fields = {"subscriber_count": subscriber_count}
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
    delivery_pattern: str | None, subscriber_count: int | None,
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
            target = remaining[0] if remaining else "SQS"

    for rule in resolution_rules:
        rule_type = rule.get("type")
        when = rule.get("when", {})
        trigger_value = when.get("value") if isinstance(when, dict) else None
        field = when.get("field") if isinstance(when, dict) else None

        if rule_type == "force" and trigger_value is not None:
            if field == "delivery_pattern" and delivery_pattern == trigger_value:
                forced = rule.get("select")
                if forced and forced in remaining:
                    target = forced
                    rubric.append(f"delivery_pattern={delivery_pattern} → force {target}")
                    return target, [], False, rubric
            if field == "subscriber_count" and subscriber_count is not None:
                op = when.get("op", "==")
                if _eval_condition(subscriber_count, op, trigger_value):
                    forced = rule.get("select")
                    if forced and forced in remaining:
                        target = forced
                        rubric.append(f"subscriber_count={subscriber_count} → force {target}")
                        return target, [], False, rubric

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


def configure(target: str, ordering_required: bool | None, ack_deadline_seconds: int | None, sizing_data: dict) -> tuple[dict, list[str]]:
    rubric = []
    aws_config = {"region": "us-east-1"}

    if target == "SNS+SQS":
        svc = sizing_data.get("sns_sqs", {})
        aws_config["pattern"] = "SNS topic → SQS subscription(s)"
        if ordering_required and svc.get("fifo_when_ordering_required"):
            aws_config["fifo"] = True
            rubric.append("ordering required → FIFO")
        if svc.get("dlq_default"):
            aws_config["dlq"] = True
        rubric.append("SNS+SQS: fan-out pattern")
    else:
        svc = sizing_data.get("sqs", {})
        aws_config["pattern"] = "SQS queue"
        if ordering_required and svc.get("fifo_when_ordering_required"):
            aws_config["fifo"] = True
            rubric.append("ordering required → FIFO")
        if svc.get("dlq_default"):
            aws_config["dlq"] = True
        if ack_deadline_seconds:
            aws_config["visibility_timeout_seconds"] = ack_deadline_seconds
        else:
            aws_config["visibility_timeout_seconds"] = svc.get("visibility_timeout_default_seconds", 30)
        rubric.append(f"SQS: visibility_timeout={aws_config['visibility_timeout_seconds']}s")

    return aws_config, rubric


def recommend_messaging_target(
    delivery_pattern: str | None = None,
    subscriber_count: int | None = None,
    ordering_required: bool | None = None,
    ack_deadline_seconds: int | None = None,
    knowledge: dict[str, Any] = None,
) -> dict:
    """Deterministic message broker recommendation.

    Funnel: DISCOVER → CONSTRAIN → RESOLVE → VERIFY → CONFIGURE
    """
    logger.info(">>> recommend_messaging_target: pattern=%s, subscribers=%s", delivery_pattern, subscriber_count)

    arch_base = "universal/archetypes/message-broker"
    definition = knowledge.get(f"{arch_base}/definition", {})
    constraints_data = knowledge.get(f"{arch_base}/constraints", {}).get("entries", [])
    resolution_rules = knowledge.get(f"{arch_base}/resolution", {}).get("priority_order", [])
    sizing_data = knowledge.get(f"{arch_base}/sizing", {})

    rubric_applied = []

    candidates, default_target = discover(definition)
    remaining, excluded, constrain_rubric = constrain(candidates, constraints_data, subscriber_count)
    rubric_applied.extend(constrain_rubric)

    target, alternatives, tie_break, resolve_rubric = resolve(
        remaining, excluded, default_target, resolution_rules, constraints_data,
        delivery_pattern, subscriber_count,
    )
    rubric_applied.extend(resolve_rubric)

    target, verify_rubric = verify(target, excluded, constraints_data)
    rubric_applied.extend(verify_rubric)

    aws_config, config_rubric = configure(target, ordering_required, ack_deadline_seconds, sizing_data)
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
