"""detect_ai_signals — scan resource list for AI workload patterns.

Pattern-matches resource types and names against known AI service prefixes
and keywords. Returns an ai_detection object for gcp-resource-inventory.json.
"""

import logging
from typing import Any

logger = logging.getLogger("migration_knowledge.detect_ai_signals")

AI_PATTERNS = [
    {"prefix": "google_vertex_ai_", "service": "vertex_ai", "confidence": 0.95},
    {"prefix": "google_bigquery_ml_", "service": "bigquery_ml", "confidence": 0.85},
    {"prefix": "google_cloud_document_ai_", "service": "document_ai", "confidence": 0.80},
    {"prefix": "google_cloud_vision_", "service": "vision_ai", "confidence": 0.80},
    {"prefix": "google_cloud_speech_", "service": "speech_ai", "confidence": 0.80},
    {"prefix": "google_cloud_translation_", "service": "translation_ai", "confidence": 0.80},
    {"prefix": "google_cloud_dialogflow_", "service": "dialogflow", "confidence": 0.80},
]

AI_NAME_KEYWORDS = ["ai", "ml", "model", "prediction", "vertex", "gemini", "palm"]


def detect_ai_signals(resources: list[dict]) -> dict:
    """Scan resources for AI workload signals.

    Args:
        resources: Flat list of resources, each with at minimum "type" and "name".

    Returns:
        ai_detection object: {has_ai_workload, confidence, confidence_level, signals_found, ai_services}
    """
    logger.info(">>> detect_ai_signals called: %d resources", len(resources))

    signals = []
    services = set()

    for res in resources:
        res_type = res.get("type", "")
        res_name = res.get("name", "")
        address = res.get("address", f"{res_type}.{res_name}")

        # Check type prefixes
        for pattern in AI_PATTERNS:
            if res_type.startswith(pattern["prefix"]):
                signals.append({
                    "resource": address,
                    "pattern": f"{pattern['prefix']}*",
                    "confidence": pattern["confidence"],
                })
                services.add(pattern["service"])
                break

        # Check name keywords (module names, etc.)
        name_lower = res_name.lower()
        for keyword in AI_NAME_KEYWORDS:
            if keyword in name_lower:
                signals.append({
                    "resource": address,
                    "pattern": f"name contains '{keyword}'",
                    "confidence": 0.70,
                })
                break

    # Compute overall confidence
    if not signals:
        overall = 0.0
        level = "none"
    else:
        overall = max(s["confidence"] for s in signals)
        if overall >= 0.90:
            level = "very_high"
        elif overall >= 0.70:
            level = "high"
        elif overall >= 0.50:
            level = "medium"
        else:
            level = "low"

    result = {
        "has_ai_workload": overall >= 0.70,
        "confidence": overall,
        "confidence_level": level,
        "signals_found": signals,
        "ai_services": sorted(services),
    }

    logger.info("<<< detect_ai_signals: has_ai=%s, confidence=%s, services=%s",
                result["has_ai_workload"], overall, list(services))
    return result
