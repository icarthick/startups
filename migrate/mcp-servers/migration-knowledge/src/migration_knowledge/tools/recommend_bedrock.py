"""Recommend Bedrock model for a source AI model migration.

Takes a source model ID + user preferences, returns the best Bedrock match
with pricing comparison and stay/migrate assessment.
"""

import logging
from typing import Any

logger = logging.getLogger("migration_knowledge.recommend_bedrock")


def _normalize_model_id(model_id: str) -> str:
    """Normalize model ID for matching (strip version suffixes, lowercase)."""
    normalized = model_id.lower().strip()
    # Strip common suffixes: -latest, -preview-*, date suffixes
    for suffix in ["-latest", "-preview"]:
        if suffix in normalized:
            normalized = normalized[:normalized.index(suffix)]
    return normalized


def _find_mapping(model_id: str, catalog: list[dict]) -> dict | None:
    """Find best matching catalog entry for a source model ID."""
    normalized = _normalize_model_id(model_id)

    # Exact match first
    for entry in catalog:
        if entry["source_id"] == normalized:
            return entry

    # Prefix match (e.g., "gpt-4o-2024-08-06" matches "gpt-4o")
    for entry in catalog:
        if normalized.startswith(entry["source_id"]):
            return entry

    # Contains match (e.g., "gemini-2.5-flash-thinking" matches "gemini-2.5-flash")
    for entry in sorted(catalog, key=lambda e: len(e["source_id"]), reverse=True):
        if entry["source_id"] in normalized:
            return entry

    return None


def _compute_savings(source_in: float | None, source_out: float | None,
                     bedrock_in: float | None, bedrock_out: float | None) -> dict:
    """Compute blended savings using 2:1 input-to-output ratio."""
    if not source_in or not bedrock_in:
        return {"blended_savings_pct": None, "cost_direction": "unknown"}

    # 2:1 input-to-output blended cost
    source_blended = (2 * source_in + (source_out or 0)) / 3
    bedrock_blended = (2 * bedrock_in + (bedrock_out or 0)) / 3

    if source_blended == 0:
        return {"blended_savings_pct": None, "cost_direction": "unknown"}

    savings_pct = round((source_blended - bedrock_blended) / source_blended * 100, 1)

    if savings_pct > 5:
        direction = "bedrock_cheaper"
    elif savings_pct < -5:
        direction = "source_cheaper"
    else:
        direction = "comparable"

    return {"blended_savings_pct": savings_pct, "cost_direction": direction}


def _assess_migration(savings: dict, priority: str | None) -> str:
    """Determine stay/migrate assessment."""
    direction = savings.get("cost_direction", "unknown")
    pct = savings.get("blended_savings_pct")

    if direction == "bedrock_cheaper":
        if pct and pct > 25:
            return "strong_migrate"
        return "moderate_migrate"
    elif direction == "source_cheaper":
        if priority == "cost" and pct and pct < -25:
            return "recommend_stay"
        return "weak_migrate"
    return "moderate_migrate"


def recommend_bedrock_model(
    source_model_id: str,
    ai_priority: str | None = None,
    ai_latency: str | None = None,
    ai_token_volume: str | None = None,
    capabilities_used: list[str] | None = None,
    knowledge: dict | None = None,
) -> dict[str, Any]:
    """Recommend a Bedrock model for a source AI model migration.

    Args:
        source_model_id: The source model ID (e.g., "gpt-4o", "gemini-2.5-flash").
        ai_priority: User priority preference ("cost", "quality", "speed", or null).
        ai_latency: Latency requirement ("critical", "flexible", or null).
        ai_token_volume: Expected volume ("low", "medium", "high", "very_high", or null).
        capabilities_used: Capabilities the workload uses (e.g., ["text_generation", "audio", "vision"]).
            Used to detect feature gaps where Bedrock lacks a required capability.
        knowledge: Knowledge store dict.

    Returns:
        Dict with bedrock recommendation, pricing, assessment, gaps, and warnings.
    """
    catalog_data = (knowledge or {}).get("universal/bedrock-model-catalog", {})
    catalog = catalog_data.get("models", [])
    overrides = catalog_data.get("preference_overrides", {})
    default = catalog_data.get("default_model", {})

    # Find base mapping
    mapping = _find_mapping(source_model_id, catalog)

    if not mapping:
        return {
            "status": "ok",
            "source_model_id": source_model_id,
            "bedrock_model_id": default.get("bedrock_id"),
            "bedrock_name": default.get("bedrock_name"),
            "source_pricing": {"input_per_1m": None, "output_per_1m": None},
            "bedrock_pricing": {"input_per_1m": default.get("bedrock_input_1m"), "output_per_1m": default.get("bedrock_output_1m")},
            "savings": {"blended_savings_pct": None, "cost_direction": "unknown"},
            "assessment": "moderate_migrate",
            "capability_gaps": [],
            "unresolved_factors": ["unknown_source_model"],
            "rationale": f"No exact mapping found for '{source_model_id}'. Defaulting to {default.get('bedrock_name')}.",
            "warnings": [],
        }

    # Apply preference overrides
    bedrock_id = mapping["bedrock_id"]
    bedrock_name = mapping["bedrock_name"]
    bedrock_in = mapping["bedrock_input_1m"]
    bedrock_out = mapping["bedrock_output_1m"]
    override_applied = None

    if ai_latency == "critical" and "latency_critical" in overrides:
        preferred = overrides["latency_critical"]["prefer_models"]
        if bedrock_id not in preferred and preferred:
            for alt in catalog:
                if alt["bedrock_id"] in preferred and alt["tier"] in ("mini", "nano", "flash"):
                    bedrock_id = alt["bedrock_id"]
                    bedrock_name = alt["bedrock_name"]
                    bedrock_in = alt["bedrock_input_1m"]
                    bedrock_out = alt["bedrock_output_1m"]
                    override_applied = "latency_critical"
                    break

    elif ai_priority == "quality" and "quality" in overrides:
        preferred = overrides["quality"]["prefer_models"]
        if bedrock_id not in preferred and preferred:
            bedrock_id = preferred[0]
            for entry in catalog:
                if entry["bedrock_id"] == bedrock_id:
                    bedrock_name = entry["bedrock_name"]
                    bedrock_in = entry["bedrock_input_1m"]
                    bedrock_out = entry["bedrock_output_1m"]
                    override_applied = "quality"
                    break

    # Compute savings
    savings = _compute_savings(mapping["input_1m"], mapping["output_1m"], bedrock_in, bedrock_out)

    # Check capability gaps
    bedrock_gaps = mapping.get("bedrock_gaps", [])
    capability_gaps = []
    if capabilities_used and bedrock_gaps:
        for cap in capabilities_used:
            if cap in bedrock_gaps:
                capability_gaps.append({
                    "capability": cap,
                    "impact": f"Source model supports '{cap}' but Bedrock target does not. Migrating would lose this functionality.",
                })

    # Assessment — gaps override price-based assessment
    if capability_gaps:
        assessment = "recommend_stay"
    else:
        assessment = _assess_migration(savings, ai_priority)

    # Unresolved factors the LLM should evaluate
    unresolved_factors = []
    if not capabilities_used:
        unresolved_factors.append("capabilities_used_not_provided")
    if ai_priority is None:
        unresolved_factors.append("user_priority_unknown")

    # Warnings
    warnings = []
    if ai_token_volume in ("high", "very_high"):
        warnings.append({
            "type": "quota_risk",
            "message": "Request Bedrock quota increase before migration (allow 1-5 business days)",
        })
    if mapping["tier"] == "embedding":
        warnings.append({
            "type": "reindex_required",
            "message": "Migrating embedding models requires re-embedding all documents in your vector store",
        })
    if mapping["tier"] == "legacy":
        warnings.append({
            "type": "legacy_source",
            "message": f"Source model '{source_model_id}' is legacy. Consider upgrading before migration.",
        })

    # Volume strategy hint
    tiered_strategy = None
    if ai_token_volume in ("high", "very_high"):
        tiered_strategy = {
            "recommended": True,
            "note": "High volume detected. Consider tiered routing: Nova Micro (60% traffic), Nova Pro (30%), Claude Sonnet (10%).",
        }

    return {
        "status": "ok",
        "source_model_id": source_model_id,
        "provider": mapping["provider"],
        "bedrock_model_id": bedrock_id,
        "bedrock_name": bedrock_name,
        "source_pricing": {"input_per_1m": mapping["input_1m"], "output_per_1m": mapping["output_1m"]},
        "bedrock_pricing": {"input_per_1m": bedrock_in, "output_per_1m": bedrock_out},
        "savings": savings,
        "assessment": assessment,
        "capability_gaps": capability_gaps,
        "unresolved_factors": unresolved_factors,
        "override_applied": override_applied,
        "rationale": f"{source_model_id} → {bedrock_name}: {savings['cost_direction']} ({savings['blended_savings_pct']}% blended)",
        "tiered_strategy": tiered_strategy,
        "warnings": warnings,
    }
