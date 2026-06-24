"""lookup_direct_mapping — checks if a source resource has an unconditional AWS target.

Pass 1 fast-path: if the source type has a direct mapping, returns the AWS target
immediately with deterministic confidence. If not, returns a miss so the caller
proceeds to normalize → recommend.
"""

import logging
from typing import Any

logger = logging.getLogger("migration_tools.lookup_direct_mapping")


def lookup_direct_mapping(
    source_type: str,
    condition_context: dict | None = None,
    knowledge: dict[str, Any] = None,
) -> dict:
    """Check if a source resource type has a direct (unconditional) AWS mapping.

    Args:
        source_type: Terraform resource type (e.g., google_storage_bucket).
        condition_context: Optional dict of fields to check conditional mappings
                          (e.g., {"engine": "sqlserver"} for SQL Server direct mapping).
        knowledge: Pre-loaded knowledge store.

    Returns:
        On hit: {"hit": true, "aws_service": "...", "confidence": "deterministic", "notes": "..."}
        On miss: {"hit": false, "reason": "..."}
    """
    logger.info(">>> lookup_direct_mapping called: source_type=%s, condition_context=%s",
                source_type, condition_context)

    # Find all direct-mapping files in knowledge store
    for key, data in knowledge.items():
        if data.get("kind") != "direct-mappings":
            continue

        for entry in data.get("entries", []):
            if entry["source_type"] != source_type:
                continue

            # Found a matching source_type — check condition
            condition = entry.get("condition")

            if condition == "always":
                logger.info("  HIT: %s → %s (condition: always)", source_type, entry["aws_service"])
                return {
                    "hit": True,
                    "aws_service": entry["aws_service"],
                    "confidence": "deterministic",
                    "notes": entry.get("notes", ""),
                }

            elif isinstance(condition, dict):
                # Conditional mapping — check all condition fields match
                if condition_context is None:
                    logger.debug("  Conditional entry found but no condition_context provided — skip")
                    continue

                all_match = all(
                    condition_context.get(k) == v
                    for k, v in condition.items()
                )
                if all_match:
                    logger.info("  HIT: %s → %s (condition matched: %s)",
                                source_type, entry["aws_service"], condition)
                    return {
                        "hit": True,
                        "aws_service": entry["aws_service"],
                        "confidence": "deterministic",
                        "notes": entry.get("notes", ""),
                    }
                else:
                    logger.debug("  Conditional entry: condition %s not matched by %s",
                                 condition, condition_context)

    logger.info("  MISS: no direct mapping for %s", source_type)
    return {
        "hit": False,
        "reason": f"No direct mapping for '{source_type}'. Proceed to normalize → recommend.",
    }
