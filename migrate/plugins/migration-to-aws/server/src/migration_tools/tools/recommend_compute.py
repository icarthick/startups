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

    # ── Load archetype knowledge ─────────────────────────────────────────────
    archetype = service_type
    valid_types = {"container", "function", "vm"}
    if archetype not in valid_types:
        return {"error": f"Unknown service_type: '{archetype}'. Valid: {list(valid_types)}"}

    arch_base = f"universal/archetypes/{archetype}"
    definition = knowledge.get(f"{arch_base}/definition", {})
    constraints_entries = knowledge.get(f"{arch_base}/constraints", {}).get("entries", [])
    resolution = knowledge.get(f"{arch_base}/resolution", {})
    sizing_data = knowledge.get(f"{arch_base}/sizing", {})

    rubric_applied = []
    default_target = definition.get("default", "Fargate")

    # ── 1. ELIMINATE → CONSTRAIN ─────────────────────────────────────────────
    excluded, elim_applied = _eliminate(timeout_seconds, vcpu, memory_gb, gpu, runtime, constraints_entries)
    rubric_applied.extend(elim_applied)
    logger.info("  CONSTRAIN: excluded=%s", excluded)

    # ── 2. DEFAULT → DISCOVER + initial target ────────────────────────────────
    target = default_target
    rubric_applied.append(f"archetype={archetype} → default {target}")
    logger.info("  DISCOVER+DEFAULT: %s", target)

    # ── 3. PREFER → RESOLVE ───────────────────────────────────────────────────
    # Build resolution config from archetype resolution.json priority_order
    k8s_map = {}
    workload_adj = {}
    cost_adj = {}
    for rule in resolution.get("priority_order", []):
        if rule.get("id") == "kubernetes-preference" and rule.get("map"):
            k8s_map = rule["map"]
        elif rule.get("type") == "adjustment":
            pattern = rule.get("when", {}).get("value")
            if pattern:
                workload_adj[pattern] = rule
        elif rule.get("type") == "force":
            pattern = rule.get("when", {}).get("value")
            if pattern:
                workload_adj[pattern] = rule
        elif rule.get("type") == "alternative":
            sense = rule.get("when", {}).get("value")
            if sense:
                cost_adj[sense] = rule

    # Apply kubernetes preference
    if kubernetes_pref and kubernetes_pref in k8s_map:
        k8s_target = k8s_map[kubernetes_pref]
        if k8s_target and k8s_target not in excluded:
            target = k8s_target
            rubric_applied.append(f"kubernetes_pref={kubernetes_pref} → {target}")
            logger.info("  RESOLVE (k8s pref): %s", target)

    # Apply workload pattern
    if workload_pattern and workload_pattern in workload_adj:
        rule = workload_adj[workload_pattern]
        if rule.get("type") == "force" and rule.get("select"):
            target = rule["select"]
            rubric_applied.append(f"workload_pattern={workload_pattern} → force {target}")
        elif rule.get("if_current") == target and rule.get("switch_to"):
            old = target
            target = rule["switch_to"]
            rubric_applied.append(f"workload_pattern={workload_pattern}: {old} → {target}")

    # Apply cost sensitivity
    alternatives = []
    tie_break_required = False
    if cost_sensitivity and cost_sensitivity in cost_adj:
        rule = cost_adj[cost_sensitivity]
        if rule.get("if_current") == target and rule.get("suggest"):
            alt = rule["suggest"]
            if alt not in excluded:
                alternatives.append({"aws_service": alt, "reason": rule.get("reason", "")})
                tie_break_required = rule.get("tie_break", False)

    logger.info("  RESOLVE: target=%s, alternatives=%s", target, [a["aws_service"] for a in alternatives])

    # ── 4. VERIFY ─────────────────────────────────────────────────────────────
    if target in excluded:
        # Find fallback
        for entry in constraints_entries:
            if entry.get("excludes") == target and entry.get("fallback"):
                fallback = entry["fallback"]
                if fallback not in excluded:
                    rubric_applied.append(f"{target} excluded → fallback {fallback}")
                    target = fallback
                    break
    logger.info("  VERIFY: target=%s", target)

    # ── 5. CONFIGURE ──────────────────────────────────────────────────────────
    aws_config = {"region": "us-east-1"}

    if target == "Fargate":
        combos = sizing_data.get("fargate", {}).get("valid_combos", [])
        snapped = _snap_to_fargate(vcpu, memory_gb, combos)
        if snapped is None:
            target = "EC2"
            rubric_applied.append("Fargate sizing exceeded limits → EC2")
            entries = sizing_data.get("ec2", {}).get("instance_mapping", [])
            aws_config["instance_type"] = _find_ec2_instance(vcpu, memory_gb, entries)
        else:
            aws_config["cpu"] = snapped["cpu"]
            aws_config["memory_gb"] = snapped["memory_gb"]
            rubric_applied.append(f"Fargate: {snapped['cpu']} vCPU / {snapped['memory_gb']} GB")

    elif target == "EC2":
        entries = sizing_data.get("ec2", {}).get("instance_mapping", [])
        instance_type = _find_ec2_instance(vcpu, memory_gb, entries)
        aws_config["instance_type"] = instance_type
        rubric_applied.append(f"EC2: {instance_type}")

    elif target == "Lambda":
        lambda_cfg = sizing_data.get("lambda", {})
        memory_mb = min(max(int(memory_gb * 1024), lambda_cfg.get("memory_min_mb", 128)), lambda_cfg.get("memory_max_mb", 10240))
        aws_config["memory_mb"] = memory_mb
        aws_config["timeout_seconds"] = min(timeout_seconds or 60, lambda_cfg.get("timeout_max_seconds", 900))
        rubric_applied.append(f"Lambda: {memory_mb}MB, {aws_config['timeout_seconds']}s")

    elif target == "EKS":
        aws_config["managed_node_group"] = True
        aws_config["notes"] = "Node pool sizing deferred to Generate phase"
        rubric_applied.append("EKS: sizing deferred to Generate")

    logger.info("  CONFIGURE: %s → %s", target, aws_config)

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
