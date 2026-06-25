"""Generate migration-preview.json from discovery artifacts.

Reads gcp-resource-inventory.json, ai-workload-profile.json, and
billing-profile.json from the migration directory, computes complexity
signals, cost estimates, and timeline hints, then writes migration-preview.json.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("migration_orchestrator.generate_preview")


def _read_json(path: Path) -> dict | None:
    """Read JSON file, return None if missing."""
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def _compute_infra_complexity(inventory: dict, billing: dict | None, ai_profile: dict | None) -> dict:
    """Compute complexity_signal for infra route."""
    resources = inventory.get("resources", [])
    primary_count = sum(1 for r in resources if r.get("classification") == "PRIMARY")
    types = {r.get("type", "") for r in resources}

    has_database = any(t.startswith("google_sql_") or t.startswith("google_spanner_") or t.startswith("google_redis_") for t in types)
    has_bigquery = any("bigquery" in t for t in types)
    is_agentic = bool(ai_profile and ai_profile.get("agentic_profile", {}).get("is_agentic"))
    billing_monthly = billing.get("summary", {}).get("total_monthly_spend") if billing else None

    if has_bigquery or is_agentic or primary_count > 8 or (billing_monthly and billing_monthly > 10000):
        signal = "complex"
    elif primary_count <= 3 and not has_database and not has_bigquery and not is_agentic and (billing_monthly is None or billing_monthly < 1000):
        signal = "likely_simple"
    else:
        signal = "standard"

    fast_path = signal == "likely_simple" and ai_profile is None
    return {
        "complexity_signal": signal,
        "primary_resource_count": primary_count,
        "has_database": has_database,
        "has_bigquery": has_bigquery,
        "eligible_for_clarify_fast_path": fast_path,
    }


def _compute_ai_complexity(ai_profile: dict) -> str:
    """Compute ai_complexity_signal from ai-workload-profile.json."""
    models = ai_profile.get("models", [])
    is_agentic = bool(ai_profile.get("agentic_profile", {}).get("is_agentic"))
    gateway = ai_profile.get("integration", {}).get("gateway_type")
    model_count = len(models)
    ai_source = ai_profile.get("summary", {}).get("ai_source", "")
    has_multi_provider = ai_source == "both"
    has_routing = gateway in ("llm_router", "openrouter", "litellm", "kong", "apigee")

    if is_agentic or has_routing or model_count > 3 or has_multi_provider:
        return "complex"
    elif model_count <= 1 and not is_agentic and not has_routing:
        caps = ai_profile.get("integration", {}).get("capabilities_summary", {})
        cap_count = sum(1 for v in caps.values() if v)
        if cap_count <= 2:
            return "likely_simple"
    return "standard"


def _compute_cost_preview(inventory: dict | None, billing: dict | None, pricing: dict) -> dict | None:
    """Compute rough AWS cost range from dev-tier pricing."""
    if not inventory and not billing:
        return None

    dev_tier = pricing.get("dev_tier_monthly", {})
    total_low = 0.0

    if inventory:
        resources = inventory.get("resources", [])
        seen_types = set()
        for r in resources:
            if r.get("classification") != "PRIMARY":
                continue
            rtype = r.get("type", "")
            if rtype in seen_types:
                continue
            seen_types.add(rtype)
            if rtype in dev_tier:
                total_low += dev_tier[rtype]["usd"]

    gcp_monthly = billing.get("summary", {}).get("total_monthly_spend") if billing else None

    return {
        "gcp_monthly_usd": gcp_monthly,
        "aws_monthly_range_usd": {"low": round(total_low, 2), "high": round(total_low * 1.5, 2)},
        "disclaimer": "Dev-tier rough estimate (+-30%); full analysis in Estimate phase",
    }


def _map_model_to_bedrock(model_id: str, pricing: dict) -> dict | None:
    """Map a source model to Bedrock equivalent using pricing-cache."""
    model_lower = model_id.lower()
    for entry in pricing.get("model_mapping", []):
        for pattern in entry["source_patterns"]:
            if pattern in model_lower:
                direction = "same"
                if entry.get("source_input_1m") and entry.get("bedrock_input_1m"):
                    if entry["bedrock_input_1m"] < entry["source_input_1m"]:
                        direction = "lower"
                    elif entry["bedrock_input_1m"] > entry["source_input_1m"]:
                        direction = "higher"
                return {
                    "source_model": model_id,
                    "source_input_per_1m": entry["source_input_1m"],
                    "source_output_per_1m": entry["source_output_1m"],
                    "bedrock_equivalent": entry["bedrock_name"],
                    "bedrock_model_id": entry["bedrock_model_id"],
                    "bedrock_input_per_1m": entry["bedrock_input_1m"],
                    "bedrock_output_per_1m": entry["bedrock_output_1m"],
                    "cost_direction": direction,
                }
    # Default mapping
    default = pricing.get("default_model_mapping", {})
    return {
        "source_model": model_id,
        "source_input_per_1m": None,
        "source_output_per_1m": None,
        "bedrock_equivalent": default.get("bedrock_name", "Amazon Nova Pro"),
        "bedrock_model_id": default.get("bedrock_model_id", "amazon.nova-pro-v1:0"),
        "bedrock_input_per_1m": default.get("bedrock_input_1m"),
        "bedrock_output_per_1m": default.get("bedrock_output_1m"),
        "cost_direction": "unknown",
    }


def _build_key_decisions(inventory: dict | None, ai_profile: dict | None, complexity: dict) -> list[str]:
    """Generate key_decisions_ahead bullets."""
    decisions = []
    if inventory:
        resources = inventory.get("resources", [])
        has_compute = any(r.get("type", "").startswith(("google_cloud_run", "google_compute", "google_container")) for r in resources)
        if has_compute:
            decisions.append("Target region and deployment model (Fargate vs EKS)")
        if complexity.get("has_database"):
            decisions.append("Database migration tooling and cutover window")
        if complexity.get("has_bigquery"):
            decisions.append("BigQuery analytics target (specialist engagement required)")

    if ai_profile:
        models = ai_profile.get("models", [])
        model_ids = [m.get("model_id", "unknown") for m in models[:3]]
        suffix = f" + {len(models) - 3} more" if len(models) > 3 else ""
        decisions.append(f"Bedrock model selection for {', '.join(model_ids)}{suffix}")
        if ai_profile.get("agentic_profile", {}).get("is_agentic"):
            decisions.append("Agentic migration path (retarget / AgentCore Harness / Strands)")

    return decisions[:4]


def _timeline_hint(signal: str, is_ai_only: bool) -> str:
    """Map complexity_signal to timeline string."""
    if is_ai_only:
        hints = {
            "likely_simple": "1-3 weeks (single model swap; confirm after Clarify)",
            "standard": "2-6 weeks (multi-model migration; confirm after Clarify)",
            "complex": "4-8 weeks (agentic or multi-provider stack; confirm after Clarify)",
        }
    else:
        hints = {
            "likely_simple": "3-6 weeks (likely simple infra; confirm after Clarify)",
            "standard": "8-12 weeks (standard migration; confirm after Clarify)",
            "complex": "12-16+ weeks (complex stack; confirm after Clarify)",
        }
    return hints.get(signal, hints["standard"])


def generate_migration_preview(migration_dir: str, knowledge: dict) -> dict[str, Any]:
    """Generate migration-preview.json from discovery artifacts.

    Reads available artifacts, computes complexity classification, cost
    estimates, timeline hints, and writes migration-preview.json.

    Args:
        migration_dir: Path to the migration run directory.
        knowledge: Knowledge store dict.

    Returns:
        Dict with status and preview summary.
    """
    mdir = Path(migration_dir)
    if not mdir.is_dir():
        return {"status": "error", "reason": f"Migration directory not found: {migration_dir}"}

    # Read discovery artifacts
    inventory = _read_json(mdir / "gcp-resource-inventory.json")
    ai_profile = _read_json(mdir / "ai-workload-profile.json")
    billing = _read_json(mdir / "billing-profile.json")
    pricing = knowledge.get("app-code/pricing-cache", {})

    if not inventory and not ai_profile and not billing:
        return {"status": "skipped", "reason": "No discovery artifacts found"}

    # Route detection
    is_ai_only = inventory is None and ai_profile is not None
    now = datetime.now(timezone.utc).isoformat()

    if is_ai_only:
        ai_signal = _compute_ai_complexity(ai_profile)
        models = ai_profile.get("models", [])
        model_ids = [m.get("model_id", "unknown") for m in models]
        is_agentic = bool(ai_profile.get("agentic_profile", {}).get("is_agentic"))
        gateway = ai_profile.get("integration", {}).get("gateway_type")
        bedrock_targets = [_map_model_to_bedrock(mid, pricing) for mid in model_ids]
        decisions = _build_key_decisions(None, ai_profile, {})

        preview = {
            "preview_version": 1,
            "computed_at": now,
            "route": "ai_only",
            "primary_resource_count": 0,
            "complexity_signal": ai_signal,
            "ai_complexity_signal": ai_signal,
            "eligible_for_clarify_fast_path": False,
            "services_summary": [],
            "ai_summary": {
                "model_count": len(models),
                "model_ids": model_ids,
                "bedrock_targets": bedrock_targets,
                "is_agentic": is_agentic,
                "has_multi_model_routing": gateway in ("llm_router", "openrouter", "litellm"),
                "gateway_type": gateway,
            },
            "cost_preview": {
                "monthly_estimate": None,
                "monthly_estimate_note": "Monthly estimate available after Clarify (usage volume collected in Q3, Q7)",
                "disclaimer": "Per-token prices from pricing-cache; full cost analysis in Estimate phase",
            },
            "timeline_hint": _timeline_hint(ai_signal, True),
            "ai_detected": True,
            "key_decisions_ahead": decisions,
        }
    else:
        # Infra route
        complexity = _compute_infra_complexity(inventory or {"resources": []}, billing, ai_profile)
        ai_signal = _compute_ai_complexity(ai_profile) if ai_profile else None
        cost_preview = _compute_cost_preview(inventory, billing, pricing)
        decisions = _build_key_decisions(inventory, ai_profile, complexity)

        # Services summary
        services_summary = []
        if inventory:
            dev_tier = pricing.get("dev_tier_monthly", {})
            seen = set()
            for r in inventory.get("resources", []):
                if r.get("classification") != "PRIMARY":
                    continue
                rtype = r.get("type", "")
                if rtype not in seen and rtype in dev_tier:
                    seen.add(rtype)
                    services_summary.append({"gcp_type": rtype, "typical_aws_target": dev_tier[rtype]["aws_target"]})

        preview = {
            "preview_version": 1,
            "computed_at": now,
            "route": "infra",
            "primary_resource_count": complexity["primary_resource_count"],
            "complexity_signal": complexity["complexity_signal"],
            "ai_complexity_signal": ai_signal,
            "eligible_for_clarify_fast_path": complexity["eligible_for_clarify_fast_path"],
            "services_summary": services_summary,
            "cost_preview": cost_preview,
            "timeline_hint": _timeline_hint(complexity["complexity_signal"], False),
            "ai_detected": ai_profile is not None,
            "key_decisions_ahead": decisions,
        }

    # Write output
    out_path = mdir / "migration-preview.json"
    with open(out_path, "w") as f:
        json.dump(preview, f, indent=2)

    return {"status": "ok", "preview": preview}
