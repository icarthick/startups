"""recommend_compute_target — deterministic compute service selection + sizing.

Follows the rubric funnel:
  1. ELIMINATE — remove services that can't physically work
  2. DEFAULT — pick the starting target for this workload type
  3. PREFER — apply user preferences to adjust the target
  4. VALIDATE — confirm the target isn't excluded; fallback if it is
  5. SIZE — produce the concrete AWS config for the chosen target
"""

import logging
from typing import Any

logger = logging.getLogger("migration_tools.recommend_compute")


# ─── Sizing helpers ───────────────────────────────────────────────────────────

def _snap_to_fargate(vcpu: float, memory_gb: float, combos: list[dict]) -> dict | None:
    """Snap source CPU/memory to the nearest valid Fargate combo (round up)."""
    for combo in combos:
        if combo["cpu"] >= vcpu and combo["memory_max_gb"] >= memory_gb:
            snapped_memory = max(memory_gb, combo["memory_min_gb"])
            return {"cpu": combo["cpu"], "memory_gb": snapped_memory}
    return None


def _find_ec2_instance(vcpu: float, memory_gb: float, entries: list[dict]) -> str:
    """Find the smallest EC2 instance type that fits the source specs."""
    for entry in entries:
        if entry["vcpu_max"] >= vcpu and entry["memory_max_gb"] >= memory_gb:
            return entry["instance_type"]
    return entries[-1]["instance_type"]


# ─── Rubric stages ────────────────────────────────────────────────────────────

def _eliminate(
    timeout_seconds: int | None, vcpu: float, memory_gb: float, gpu: bool,
    runtime: str | None, eliminators: list[dict]
) -> tuple[set[str], list[str]]:
    """Stage 1: ELIMINATE — identify services that can't work for this resource."""
    excluded = set()
    applied = []

    for elim in eliminators:
        # Unconditional forbids (e.g., App Runner)
        if elim.get("forbids"):
            excluded.add(elim["forbids"])
            applied.append(f"{elim['id']}: {elim['forbids']} forbidden")
            continue

        # Conditional eliminators
        triggered = False
        when = elim.get("when")

        if when == "always":
            triggered = True
        elif isinstance(when, dict):
            fields = {"timeout_seconds": timeout_seconds, "vcpu": vcpu, "memory_gb": memory_gb, "gpu": gpu}

            # Single condition
            if "field" in when:
                val = fields.get(when["field"])
                if val is not None:
                    triggered = _eval_condition(val, when["op"], when["value"])

            # OR compound (any)
            if "any" in when:
                for cond in when["any"]:
                    val = fields.get(cond.get("field"))
                    if val is not None and _eval_condition(val, cond["op"], cond["value"]):
                        triggered = True
                        break

        if triggered and elim.get("excludes"):
            excluded.add(elim["excludes"])
            applied.append(f"eliminator: {elim['id']} → exclude {elim['excludes']}")

    # Runtime-specific eliminator (not in JSON — Python 2.7 is a special case)
    if runtime and "python2" in runtime.lower():
        excluded.add("Lambda")
        applied.append("eliminator: python2.7 → exclude Lambda")

    return excluded, applied


def _default_target(service_type: str, config: dict) -> tuple[str, str]:
    """Stage 2: DEFAULT — pick the starting target for this workload type."""
    target = config["default_targets"].get(service_type)
    if target is None:
        return "Fargate", f"service_type={service_type} → default Fargate (fallback)"
    return target, f"service_type={service_type} → default {target}"


def _apply_preferences(
    target: str, workload_pattern: str | None, cost_sensitivity: str | None,
    kubernetes_pref: str | None, excluded: set[str], config: dict
) -> tuple[str, list[str], list[dict], bool]:
    """Stage 3: PREFER — adjust target based on K8s preference, workload pattern, cost sensitivity."""
    applied = []
    alternatives = []
    tie_break = False

    # Kubernetes preference (overrides default for container workloads)
    if kubernetes_pref:
        k8s_map = config.get("kubernetes_preference_map", {})
        if kubernetes_pref in k8s_map:
            k8s_target = k8s_map[kubernetes_pref]
            if k8s_target not in excluded:
                old = target
                target = k8s_target
                applied.append(f"kubernetes_pref={kubernetes_pref} → {target}")

    # Workload pattern adjustments
    if workload_pattern:
        adj = config.get("workload_adjustments", {}).get(workload_pattern)
        if adj:
            if adj.get("force"):
                target = adj["force"]
                applied.append(f"workload_pattern={workload_pattern} → force {target}")
            elif adj.get("if_default") == target and adj.get("switch_to"):
                old = target
                target = adj["switch_to"]
                applied.append(f"workload_pattern={workload_pattern}: {old} → {target}")

    # Cost sensitivity
    if cost_sensitivity:
        cost_adj = config.get("cost_sensitivity_adjustments", {}).get(cost_sensitivity)
        if cost_adj and cost_adj.get("if_default") == target:
            alt = cost_adj["suggest_alternative"]
            if alt not in excluded:
                alternatives.append({"aws_service": alt, "reason": cost_adj["reason"]})
                tie_break = cost_adj.get("tie_break", False)
                applied.append(f"cost_sensitivity={cost_sensitivity} → alternative {alt}")

    return target, applied, alternatives, tie_break


def _validate_target(target: str, excluded: set[str], eliminators: list[dict]) -> tuple[str, str | None]:
    """Stage 4: VALIDATE — confirm target isn't excluded; find fallback if it is."""
    if target not in excluded:
        return target, None

    for elim in eliminators:
        if elim.get("excludes") == target and elim.get("fallback"):
            fallback = elim["fallback"]
            if fallback not in excluded:
                return fallback, f"{target} excluded → fallback {fallback}"

    return target, None  # shouldn't happen with valid data


def _size(target: str, vcpu: float, memory_gb: float, timeout_seconds: int | None, config: dict) -> tuple[dict, str]:
    """Stage 5: SIZE — produce concrete AWS config for the chosen target."""
    aws_config = {"region": "us-east-1"}

    if target == "Fargate":
        snapped = _snap_to_fargate(vcpu, memory_gb, config["fargate_valid_combos"]["combos"])
        if snapped is None:
            # Exceeded limits — fall to EC2
            instance_type = _find_ec2_instance(vcpu, memory_gb, config["ec2_instance_mapping"]["entries"])
            aws_config["instance_type"] = instance_type
            return aws_config, f"Fargate limits exceeded → EC2 {instance_type}"
        aws_config["cpu"] = snapped["cpu"]
        aws_config["memory_gb"] = snapped["memory_gb"]
        return aws_config, f"Fargate: snapped to {snapped['cpu']} vCPU / {snapped['memory_gb']} GB"

    elif target == "EC2":
        instance_type = _find_ec2_instance(vcpu, memory_gb, config["ec2_instance_mapping"]["entries"])
        aws_config["instance_type"] = instance_type
        return aws_config, f"EC2: {instance_type}"

    elif target == "Lambda":
        lambda_cfg = config["lambda_config"]
        memory_mb = min(max(int(memory_gb * 1024), lambda_cfg["memory_min_mb"]), lambda_cfg["memory_max_mb"])
        aws_config["memory_mb"] = memory_mb
        aws_config["timeout_seconds"] = min(timeout_seconds or 60, lambda_cfg["timeout_max_seconds"])
        return aws_config, f"Lambda: {memory_mb}MB, {aws_config['timeout_seconds']}s"

    elif target == "EKS":
        aws_config["managed_node_group"] = True
        aws_config["notes"] = "Node pool sizing deferred to Generate phase"
        return aws_config, "EKS: sizing deferred to Generate"

    return aws_config, f"{target}: no sizing rules"


# ─── Condition evaluator ──────────────────────────────────────────────────────

def _eval_condition(value, op: str, threshold) -> bool:
    if op == ">" and value > threshold:
        return True
    if op == ">=" and value >= threshold:
        return True
    if op == "==" and value == threshold:
        return True
    if op == "!=" and value != threshold:
        return True
    if op == "<" and value < threshold:
        return True
    if op == "<=" and value <= threshold:
        return True
    return False


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

    Rubric funnel: ELIMINATE → DEFAULT → PREFER → VALIDATE → SIZE
    """
    logger.info(">>> recommend_compute_target called")
    logger.info("  input: service_type=%s, timeout=%s, vcpu=%s, memory_gb=%s, gpu=%s, runtime=%s, workload_pattern=%s, k8s_pref=%s, cost_sensitivity=%s",
                service_type, timeout_seconds, vcpu, memory_gb, gpu, runtime, workload_pattern, kubernetes_pref, cost_sensitivity)

    config = knowledge["universal/compute/service-configuration"]
    eliminators = knowledge["universal/eliminators"]["entries"]
    rubric_applied = []

    # Validate service_type
    if service_type not in config["default_targets"]:
        return {"error": f"Unknown service_type: '{service_type}'. Valid: {list(config['default_targets'].keys())}"}

    # ── 1. ELIMINATE ──────────────────────────────────────────────────────────
    excluded, elim_applied = _eliminate(timeout_seconds, vcpu, memory_gb, gpu, runtime, eliminators)
    rubric_applied.extend(elim_applied)
    logger.info("  ELIMINATE: excluded=%s", excluded)

    # ── 2. DEFAULT ────────────────────────────────────────────────────────────
    target, default_reason = _default_target(service_type, config)
    rubric_applied.append(default_reason)
    logger.info("  DEFAULT: %s", target)

    # ── 3. PREFER ─────────────────────────────────────────────────────────────
    target, pref_applied, alternatives, tie_break_required = _apply_preferences(
        target, workload_pattern, cost_sensitivity, kubernetes_pref, excluded, config
    )
    rubric_applied.extend(pref_applied)
    logger.info("  PREFER: target=%s, alternatives=%s", target, [a["aws_service"] for a in alternatives])

    # ── 4. VALIDATE ───────────────────────────────────────────────────────────
    target, validate_reason = _validate_target(target, excluded, eliminators)
    if validate_reason:
        rubric_applied.append(validate_reason)
    logger.info("  VALIDATE: target=%s (fallback applied: %s)", target, validate_reason is not None)

    # ── 5. SIZE ───────────────────────────────────────────────────────────────
    aws_config, size_reason = _size(target, vcpu, memory_gb, timeout_seconds, config)
    rubric_applied.append(size_reason)
    logger.info("  SIZE: %s", size_reason)

    # ── Assemble result ───────────────────────────────────────────────────────
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

    logger.info("<<< recommend_compute_target returning: aws_service=%s", target)
    return result
