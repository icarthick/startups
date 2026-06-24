"""lookup_direct_mapping — checks if a source resource has an immediate resolution.

Pass 1 fast-path: checks direct mappings, skip mappings, and specialist gates.
If any match, returns the result immediately — no further tools needed.
If none match, returns a miss so the caller proceeds to normalize → recommend.
"""

import logging
from typing import Any

logger = logging.getLogger("migration_tools.lookup_direct_mapping")


def lookup_direct_mapping(
    source_type: str,
    condition_context: dict | None = None,
    knowledge: dict[str, Any] = None,
) -> dict:
    """Check if a source resource type has an immediate resolution (direct, skip, or deferred).

    Args:
        source_type: Terraform resource type (e.g., google_storage_bucket).
        condition_context: Optional dict of fields to check conditional mappings
                          (e.g., {"engine": "sqlserver"} for SQL Server direct mapping).
        knowledge: Pre-loaded knowledge store.

    Returns:
        On direct hit: {"hit": true, "type": "direct", "aws_service": "...", "confidence": "deterministic", ...}
        On skip hit: {"hit": true, "type": "skip", "reason": "..."}
        On deferred hit: {"hit": true, "type": "deferred", "aws_service": "Deferred — specialist engagement", ...}
        On miss: {"hit": false, "reason": "..."}
    """
    logger.info(">>> lookup_direct_mapping called: source_type=%s, condition_context=%s",
                source_type, condition_context)

    # --- Check specialist gates (prefix-based) ---
    specialist_prefixes = {
        "google_bigquery_": {
            "aws_service": "Deferred — specialist engagement",
            "human_expertise_required": True,
            "confidence": "inferred",
            "reason": "Engage AWS account team and/or data analytics migration partner before choosing any AWS target.",
            "rubric_applied": ["BigQuery specialist gate — no automated AWS service target"],
        }
    }

    for prefix, gate_result in specialist_prefixes.items():
        if source_type.startswith(prefix):
            logger.info("  HIT (deferred): %s matches specialist gate prefix '%s'", source_type, prefix)
            return {"hit": True, "type": "deferred", **gate_result}

    # --- Check skip mappings ---
    for key, data in knowledge.items():
        if data.get("kind") != "skip-mappings":
            continue

        for entry in data.get("entries", []):
            skip_type = entry["source_type"]
            # Support wildcard suffix (e.g., "google_monitoring_*")
            if skip_type.endswith("*"):
                if source_type.startswith(skip_type[:-1]):
                    logger.info("  HIT (skip): %s matches skip pattern '%s'", source_type, skip_type)
                    return {"hit": True, "type": "skip", "reason": entry["reason"]}
            elif source_type == skip_type:
                logger.info("  HIT (skip): %s exact match", source_type)
                return {"hit": True, "type": "skip", "reason": entry["reason"]}

    # --- Check direct mappings ---
    for key, data in knowledge.items():
        if data.get("kind") != "direct-mappings":
            continue

        for entry in data.get("entries", []):
            if entry["source_type"] != source_type:
                continue

            condition = entry.get("condition")

            if condition == "always":
                logger.info("  HIT (direct): %s → %s (condition: always)", source_type, entry["aws_service"])
                return {
                    "hit": True,
                    "type": "direct",
                    "aws_service": entry["aws_service"],
                    "confidence": "deterministic",
                    "notes": entry.get("notes", ""),
                }

            elif isinstance(condition, dict):
                if condition_context is None:
                    logger.debug("  Conditional entry found but no condition_context provided — skip")
                    continue

                all_match = all(
                    condition_context.get(k) == v
                    for k, v in condition.items()
                )
                if all_match:
                    logger.info("  HIT (direct): %s → %s (condition matched: %s)",
                                source_type, entry["aws_service"], condition)
                    return {
                        "hit": True,
                        "type": "direct",
                        "aws_service": entry["aws_service"],
                        "confidence": "deterministic",
                        "notes": entry.get("notes", ""),
                    }
                else:
                    logger.debug("  Conditional entry: condition %s not matched by %s",
                                 condition, condition_context)

    logger.info("  MISS: no direct/skip/deferred mapping for %s", source_type)
    return {
        "hit": False,
        "reason": f"No direct mapping for '{source_type}'. Proceed to normalize → recommend.",
    }
