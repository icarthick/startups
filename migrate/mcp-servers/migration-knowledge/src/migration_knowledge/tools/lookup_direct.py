"""lookup_direct_mapping — checks if a source resource has an immediate resolution.

Pass 1 fast-path: checks direct mappings, skip mappings, and specialist gates.
If any match, returns the result immediately — no further tools needed.
If none match, returns a miss so the caller proceeds to normalize → recommend.
"""

import logging
from typing import Any

logger = logging.getLogger("migration_tools.lookup_direct_mapping")


# Condition extraction rules: source_type → how to derive condition fields from raw_config
_CONDITION_EXTRACTORS: dict[str, dict] = {
    "google_sql_database_instance": {
        "field": "database_version",
        "output_key": "engine",
        "transform": {
            "POSTGRES": "postgres",
            "MYSQL": "mysql",
            "SQLSERVER": "sqlserver",
        },
    },
}


def _extract_condition_context(source_type: str, raw_config: dict) -> dict | None:
    """Auto-extract condition fields from raw_config for known source types."""
    extractor = _CONDITION_EXTRACTORS.get(source_type)
    if not extractor:
        return None

    raw_value = raw_config.get(extractor["field"])
    if not raw_value or not isinstance(raw_value, str):
        return None

    # Match by prefix (e.g., "POSTGRES_15" starts with "POSTGRES")
    for prefix, mapped_value in extractor["transform"].items():
        if raw_value.upper().startswith(prefix):
            return {extractor["output_key"]: mapped_value}

    return None


def lookup_direct_mapping(
    source_type: str,
    condition_context: dict | None = None,
    raw_config: dict | None = None,
    knowledge: dict[str, Any] = None,
) -> dict:
    """Check if a source resource type has an immediate resolution (direct, skip, or deferred).

    Args:
        source_type: Terraform resource type (e.g., google_storage_bucket).
        condition_context: Optional dict of fields to check conditional mappings
                          (e.g., {"engine": "sqlserver"} for SQL Server direct mapping).
        raw_config: Optional raw resource config. If provided and condition_context
                    is not, the tool will auto-extract condition fields from config
                    (e.g., database_version → engine for Cloud SQL).
        knowledge: Pre-loaded knowledge store.

    Returns:
        On direct hit: {"hit": true, "type": "direct", "aws_service": "...", "confidence": "deterministic", ...}
        On skip hit: {"hit": true, "type": "skip", "reason": "..."}
        On deferred hit: {"hit": true, "type": "deferred", "aws_service": "Deferred — specialist engagement", ...}
        On miss: {"hit": false, "reason": "..."}
    """
    logger.info(">>> lookup_direct_mapping called: source_type=%s, condition_context=%s",
                source_type, condition_context)

    # Auto-extract condition_context from raw_config if not provided
    if condition_context is None and raw_config is not None:
        condition_context = _extract_condition_context(source_type, raw_config)
        if condition_context:
            logger.info("  auto-extracted condition_context=%s from raw_config", condition_context)

    # --- Check deferred mappings (specialist gates, from knowledge file) ---
    for key, data in knowledge.items():
        if data.get("kind") != "deferred-mappings":
            continue
        for entry in data.get("entries", []):
            prefix = entry.get("prefix", "")
            if source_type.startswith(prefix):
                logger.info("  HIT (deferred): %s matches prefix '%s'", source_type, prefix)
                return {
                    "hit": True,
                    "type": "deferred",
                    "aws_service": entry["aws_service"],
                    "human_expertise_required": entry.get("human_expertise_required", True),
                    "confidence": entry.get("confidence", "inferred"),
                    "reason": entry.get("reason", ""),
                    "rubric_applied": entry.get("rubric_applied", []),
                }

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
