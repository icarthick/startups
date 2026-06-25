"""create_ai_profile_from_iac — write ai-workload-profile.json from IaC signals.

Produces a minimal profile when Vertex AI resources are detected in Terraform.
The LLM decides ai_source (gemini vs other); the tool writes the file with
guaranteed correct schema.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger("migration_knowledge.create_ai_profile_from_iac")


def create_ai_profile_from_iac(
    ai_source: str,
    ai_detection: dict,
    vertex_resources: list[dict],
    migration_dir: str,
) -> dict:
    """Write ai-workload-profile.json from IaC-inferred Vertex AI signals.

    Args:
        ai_source: LLM-determined source — "gemini" (generative) or "other" (traditional ML).
        ai_detection: Output from detect_ai_signals (confidence, signals, services).
        vertex_resources: List of Vertex AI resources from the inventory
            (each with address, type, config).
        migration_dir: Directory to write ai-workload-profile.json.

    Returns:
        {"status": "written", "file": "ai-workload-profile.json"}
    """
    logger.info(">>> create_ai_profile_from_iac: ai_source=%s, %d vertex resources",
                ai_source, len(vertex_resources))

    profile = {
        "metadata": {
            "profile_source": "iac_vertex",
            "sources_analyzed": {
                "terraform": True,
                "application_code": False,
                "billing_data": False,
            },
        },
        "summary": {
            "overall_confidence": ai_detection.get("confidence", 0),
            "confidence_level": ai_detection.get("confidence_level", "none"),
            "total_models_detected": 0,
            "languages_found": [],
            "inferred_from_iac": True,
            "ai_source": ai_source,
        },
        "models": [],
        "integration": {
            "primary_sdk": None,
            "frameworks": [],
            "languages": [],
            "pattern": "unknown",
            "gateway_type": None,
            "capabilities_summary": {
                "chat": False,
                "embeddings": False,
                "image_generation": False,
                "code_generation": False,
                "function_calling": False,
                "streaming": False,
                "batch": False,
                "fine_tuning": False,
                "rag": False,
            },
        },
        "infrastructure": [
            {"address": r.get("address"), "type": r.get("type"), "config": r.get("config", {})}
            for r in vertex_resources
        ],
        "detection_signals": [
            {"method": "terraform", "pattern": s.get("pattern"), "confidence": s.get("confidence"), "evidence": s.get("resource")}
            for s in ai_detection.get("signals_found", [])
        ],
    }

    out_path = Path(migration_dir) / "ai-workload-profile.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(profile, indent=2) + "\n")

    logger.info("<<< wrote ai-workload-profile.json to %s", migration_dir)
    return {"status": "written", "file": "ai-workload-profile.json"}
