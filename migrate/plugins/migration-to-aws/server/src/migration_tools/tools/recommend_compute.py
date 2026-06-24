"""recommend_compute_target — deterministic compute service selection + sizing.

Takes canonical compute inputs (service_type, resource specs, preferences,
LLM-inferred workload_pattern), applies eliminators → default → preferences →
adjustments → sizing. Returns AWS service + config.
"""

import logging
from typing import Any

logger = logging.getLogger("migration_tools.recommend_compute")


def _snap_to_fargate(vcpu: float, memory_gb: float, combos: list[dict]) -> dict:
    """Snap source CPU/memory to the nearest valid Fargate combo (round up)."""
    for combo in combos:
        if combo["cpu"] >= vcpu and combo["memory_max_gb"] >= memory_gb:
            # Snap memory to at least the min for this CPU tier
            snapped_memory = max(memory_gb, combo["memory_min_gb"])
            return {"cpu": combo["cpu"], "memory_gb": snapped_memory}
    # Exceeded all combos → not Fargate-eligible
    return None


def _find_ec2_instance(vcpu: float, memory_gb: float, entries: list[dict]) -> str:
    """Find the smallest EC2 instance type that fits the source specs."""
    for entry in entries:
        if entry["vcpu_max"] >= vcpu and entry["memory_max_gb"] >= memory_gb:
            return entry["instance_type"]
    return entries[-1]["instance_type"]  # largest available


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
    """Deterministic compute target recommendation."""
    logger.info(">>> recommend_compute_target called")
    logger.info("  input: service_type=%s, timeout=%s, vcpu=%s, memory_gb=%s, gpu=%s, runtime=%s, workload_pattern=%s, k8s_pref=%s, cost_sensitivity=%s",
                service_type, timeout_seconds, vcpu, memory_gb, gpu, runtime, workload_pattern, kubernetes_pref, cost_sensitivity)

    config = knowledge["universal/compute/service-configuration"]
    eliminators = knowledge["universal/eliminators"]["entries"]
    rubric_applied = []
    warnings = []
    excluded_services = set()

    # --- Step 1: Apply eliminators ---
    logger.debug("Step 1: checking eliminators")

    # App Runner — always forbidden
    excluded_services.add("App Runner")
    rubric_applied.append("App Runner forbidden (closed to new customers)")

    for elim in eliminators:
        if elim.get("forbids"):
            excluded_services.add(elim["forbids"])
            continue

        triggered = False
        when = elim.get("when")
        if when == "always":
            triggered = True
        elif isinstance(when, dict):
            field_val = {"timeout_seconds": timeout_seconds, "vcpu": vcpu, "memory_gb": memory_gb, "gpu": gpu}.get(when.get("field"))
            if field_val is not None:
                op = when["op"]
                threshold = when["value"]
                if op == ">" and field_val > threshold:
                    triggered = True
                elif op == ">=" and field_val >= threshold:
                    triggered = True
                elif op == "==" and field_val == threshold:
                    triggered = True
            # Handle "any" conditions
            if "any" in when:
                for cond in when["any"]:
                    fv = {"timeout_seconds": timeout_seconds, "vcpu": vcpu, "memory_gb": memory_gb, "gpu": gpu}.get(cond.get("field"))
                    if fv is not None:
                        if cond["op"] == ">" and fv > cond["value"]:
                            triggered = True
                        elif cond["op"] == "==" and fv == cond["value"]:
                            triggered = True

        if triggered and elim.get("excludes"):
            excluded_services.add(elim["excludes"])
            rubric_applied.append(f"eliminator: {elim['id']} → exclude {elim['excludes']}")
            logger.info("  Eliminator triggered: %s → exclude %s", elim["id"], elim["excludes"])

    # Check runtime eliminator (Python 2.7 → exclude Lambda)
    if runtime and "python2" in runtime.lower():
        excluded_services.add("Lambda")
        rubric_applied.append("eliminator: python2.7 → exclude Lambda")
        logger.info("  Eliminator: python2.7 runtime → exclude Lambda")

    logger.info("  Excluded services after eliminators: %s", excluded_services)

    # --- Step 2: Determine default target ---
    logger.debug("Step 2: default target by service_type")
    default_targets = config["default_targets"]

    if service_type not in default_targets:
        return {"error": f"Unknown service_type: '{service_type}'. Valid: {list(default_targets.keys())}"}

    if service_type == "kubernetes":
        # Special: driven by preference
        k8s_map = config["kubernetes_preference_map"]
        pref_key = kubernetes_pref if kubernetes_pref in k8s_map else "absent"
        target = k8s_map[pref_key]
        rubric_applied.append(f"kubernetes_pref={pref_key} → {target}")
        logger.info("  Kubernetes preference: %s → %s", pref_key, target)
    else:
        target = default_targets[service_type]
        rubric_applied.append(f"service_type={service_type} → default {target}")
        logger.info("  Default target: %s → %s", service_type, target)

    # --- Step 3: Apply workload pattern adjustments ---
    logger.debug("Step 3: workload pattern adjustments")
    if workload_pattern:
        adjustments = config.get("workload_adjustments", {})
        adj = adjustments.get(workload_pattern)
        if adj:
            if adj.get("force"):
                target = adj["force"]
                rubric_applied.append(f"workload_pattern={workload_pattern} → force {target}")
                logger.info("  Workload adjustment: force %s (%s)", target, adj.get("reason", ""))
            elif adj.get("if_default") == target and adj.get("switch_to"):
                old_target = target
                target = adj["switch_to"]
                rubric_applied.append(f"workload_pattern={workload_pattern}: {old_target} → {target}")
                logger.info("  Workload adjustment: %s → %s (%s)", old_target, target, adj.get("reason", ""))

    # --- Step 4: Check if target is excluded ---
    alternatives = []
    tie_break_required = False

    if target in excluded_services:
        # Find fallback from eliminators
        for elim in eliminators:
            if elim.get("excludes") == target and elim.get("fallback"):
                fallback = elim["fallback"]
                if fallback not in excluded_services:
                    rubric_applied.append(f"{target} excluded → fallback {fallback}")
                    logger.info("  Target %s excluded, falling back to %s", target, fallback)
                    target = fallback
                    break
        else:
            # No fallback found — this shouldn't happen with valid data
            return {"error": f"Target '{target}' is excluded and no valid fallback found. Excluded: {excluded_services}"}

    # --- Step 5: Cost sensitivity alternative ---
    if cost_sensitivity:
        cost_adj = config.get("cost_sensitivity_adjustments", {}).get(cost_sensitivity)
        if cost_adj and cost_adj.get("if_default") == target:
            alt = cost_adj["suggest_alternative"]
            if alt not in excluded_services:
                alternatives.append({"aws_service": alt, "reason": cost_adj["reason"]})
                tie_break_required = cost_adj.get("tie_break", False)
                logger.info("  Cost sensitivity: suggesting %s as alternative to %s", alt, target)

    # --- Step 6: Sizing ---
    logger.debug("Step 6: sizing for %s", target)
    aws_config = {"region": "us-east-1"}

    if target == "Fargate":
        combos = config["fargate_valid_combos"]["combos"]
        snapped = _snap_to_fargate(vcpu, memory_gb, combos)
        if snapped is None:
            # Exceeded Fargate limits — shouldn't happen if eliminators worked
            target = "EC2"
            rubric_applied.append("Fargate sizing exceeded limits → EC2")
            logger.warning("  Fargate snap failed (vcpu=%s, mem=%s), falling back to EC2", vcpu, memory_gb)
            instance_type = _find_ec2_instance(vcpu, memory_gb, config["ec2_instance_mapping"]["entries"])
            aws_config["instance_type"] = instance_type
        else:
            aws_config["cpu"] = snapped["cpu"]
            aws_config["memory_gb"] = snapped["memory_gb"]
            rubric_applied.append(f"Fargate sizing: {vcpu} vCPU / {memory_gb} GB → snapped to {snapped['cpu']} vCPU / {snapped['memory_gb']} GB")
            logger.info("  Fargate sizing: snapped to cpu=%s, memory=%s GB", snapped["cpu"], snapped["memory_gb"])

    elif target == "EC2":
        instance_type = _find_ec2_instance(vcpu, memory_gb, config["ec2_instance_mapping"]["entries"])
        aws_config["instance_type"] = instance_type
        rubric_applied.append(f"EC2 sizing: {vcpu} vCPU / {memory_gb} GB → {instance_type}")
        logger.info("  EC2 sizing: %s", instance_type)

    elif target == "Lambda":
        lambda_cfg = config["lambda_config"]
        memory_mb = min(max(int(memory_gb * 1024), lambda_cfg["memory_min_mb"]), lambda_cfg["memory_max_mb"])
        aws_config["memory_mb"] = memory_mb
        aws_config["timeout_seconds"] = min(timeout_seconds or 60, lambda_cfg["timeout_max_seconds"])
        rubric_applied.append(f"Lambda sizing: memory={memory_mb}MB, timeout={aws_config['timeout_seconds']}s")
        logger.info("  Lambda sizing: memory=%sMB, timeout=%ss", memory_mb, aws_config["timeout_seconds"])

    elif target == "EKS":
        aws_config["managed_node_group"] = True
        aws_config["notes"] = "Node pool sizing deferred to Generate phase"
        rubric_applied.append("EKS: node pool sizing deferred to Generate")
        logger.info("  EKS: sizing deferred to Generate")

    result = {
        "aws_service": target,
        "aws_config": aws_config,
        "confidence": "inferred",
        "human_expertise_required": False,
        "rubric_applied": rubric_applied,
        "alternatives": alternatives,
        "tie_break_required": tie_break_required,
        "warnings": warnings,
    }

    logger.info("<<< recommend_compute_target returning: aws_service=%s, config=%s", target, aws_config)
    return result
