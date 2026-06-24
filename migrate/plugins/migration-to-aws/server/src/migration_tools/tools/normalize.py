"""normalize_resource — translates source-native config to canonical model.

Reads the per-source normalization.json, applies field extraction + transforms,
returns canonical fields ready for recommend_* tools. Flags fields that need
LLM inference.
"""

import logging
import re
from typing import Any

logger = logging.getLogger("migration_tools.normalize_resource")


def _resolve_path(config: dict, path: str) -> Any:
    """Resolve a dotted path (e.g., 'settings.tier') against a nested dict."""
    parts = path.split(".")
    current = config
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
        if current is None:
            return None
    return current


def _match_transform(value: Any, transform: dict) -> Any:
    """Match a value against transform patterns (supports trailing * as wildcard)."""
    # Handle presence/absence check (for fields like gpu where value is a list or truthy/falsy)
    if "present" in transform and "absent" in transform:
        if value and value != [] and value != {}:
            return transform["present"]
        else:
            return transform["absent"]

    if not isinstance(value, str):
        # Non-string scalar: try exact match
        if isinstance(value, (int, float, bool)) and value in transform:
            return transform[value]
        return None

    # Try exact match first
    if value in transform:
        return transform[value]

    # Try wildcard patterns (e.g., "POSTGRES_*" matches "POSTGRES_15")
    for pattern, result in transform.items():
        if isinstance(pattern, str) and pattern.endswith("*"):
            prefix = pattern[:-1]
            if value.startswith(prefix):
                return result

    return None


def normalize_resource(
    source_type: str,
    raw_config: dict,
    knowledge: dict[str, Any] = None,
) -> dict:
    """Normalize a source resource to canonical model fields.

    Args:
        source_type: Terraform resource type (e.g., google_sql_database_instance).
        raw_config: Raw resource config dict from inventory.
        knowledge: Pre-loaded knowledge store.

    Returns:
        canonical_workload, canonical_fields, unmapped_fields, requires_inference.
    """
    logger.info(">>> normalize_resource called: source_type=%s", source_type)
    logger.debug("  raw_config keys: %s", list(raw_config.keys()) if raw_config else [])

    # Find the normalization entry for this source_type
    norm_entry = None
    for key, data in knowledge.items():
        if data.get("kind") != "normalization":
            continue
        for entry in data.get("entries", []):
            if entry["source_type"] == source_type:
                norm_entry = entry
                break
        if norm_entry:
            break

    if norm_entry is None:
        logger.warning("  No normalization entry found for source_type=%s", source_type)
        return {
            "canonical_workload": None,
            "canonical_fields": {},
            "unmapped_fields": list(raw_config.keys()) if raw_config else [],
            "requires_inference": [],
            "error": f"No normalization entry for source_type '{source_type}'"
        }

    canonical_workload = norm_entry["canonical_workload"]
    field_map = norm_entry.get("field_map", {})
    canonical_fields = {}
    requires_inference = []

    logger.info("  Found entry: canonical_workload=%s, field_map keys=%s",
                canonical_workload, list(field_map.keys()))

    for canonical_name, mapping in field_map.items():
        if isinstance(mapping, str):
            # Literal value (e.g., "engine": "postgres") or simple field reference
            if mapping.startswith("from:"):
                # Shorthand: "from:field_path"
                path = mapping[5:]
                value = _resolve_path(raw_config, path)
                if value is not None:
                    canonical_fields[canonical_name] = value
                    logger.debug("  %s: from:%s → %s", canonical_name, path, value)
                else:
                    requires_inference.append(canonical_name)
                    logger.debug("  %s: from:%s → None (requires inference)", canonical_name, path)
            else:
                # Literal value
                canonical_fields[canonical_name] = mapping
                logger.debug("  %s: literal → %s", canonical_name, mapping)

        elif isinstance(mapping, (int, float, bool)):
            # Literal numeric/boolean
            canonical_fields[canonical_name] = mapping
            logger.debug("  %s: literal → %s", canonical_name, mapping)

        elif isinstance(mapping, dict):
            # Complex mapping with "from" + optional "transform"
            source_path = mapping.get("from", "")
            transform = mapping.get("transform", {})

            raw_value = _resolve_path(raw_config, source_path)

            if raw_value is None:
                requires_inference.append(canonical_name)
                logger.debug("  %s: from=%s → None (requires inference)", canonical_name, source_path)
                continue

            if transform:
                transformed = _match_transform(raw_value, transform)
                if transformed is not None:
                    canonical_fields[canonical_name] = transformed
                    logger.debug("  %s: %s → transform → %s", canonical_name, raw_value, transformed)
                else:
                    # Value exists but no transform matched — pass raw + flag
                    canonical_fields[canonical_name] = raw_value
                    logger.debug("  %s: %s → no transform match, using raw", canonical_name, raw_value)
            else:
                # No transform — pass through raw value
                canonical_fields[canonical_name] = raw_value
                logger.debug("  %s: %s → passthrough", canonical_name, raw_value)

    # Determine unmapped fields (raw config keys not referenced by any field_map entry)
    referenced_paths = set()
    for mapping in field_map.values():
        if isinstance(mapping, dict) and "from" in mapping:
            referenced_paths.add(mapping["from"].split(".")[0])
        elif isinstance(mapping, str) and mapping.startswith("from:"):
            referenced_paths.add(mapping[5:].split(".")[0])

    unmapped_fields = [k for k in (raw_config or {}).keys() if k not in referenced_paths]

    # Add known inference-required fields based on canonical_workload
    workload_inference_fields = {
        "container": ["workload_pattern"],
        "function": ["workload_pattern"],
        "vm": ["workload_pattern"],
        "kubernetes": [],
        "relational-db": [],
        "nosql-document": [],
    }
    for field in workload_inference_fields.get(canonical_workload, []):
        if field not in canonical_fields and field not in requires_inference:
            requires_inference.append(field)

    # Map canonical_workload to the next tool to call
    workload_to_tool = {
        "relational-db": "recommend_database",
        "container": "recommend_compute",
        "function": "recommend_compute",
        "vm": "recommend_compute",
        "kubernetes": "recommend_compute",
        "app-engine": "recommend_compute",
        "nosql-document": None,  # No tool yet — manual rubric fallback
    }
    next_tool = workload_to_tool.get(canonical_workload)

    result = {
        "canonical_workload": canonical_workload,
        "next_tool": next_tool,
        "canonical_fields": canonical_fields,
        "unmapped_fields": unmapped_fields,
        "requires_inference": requires_inference,
    }

    logger.info("<<< normalize_resource returning: workload=%s, next_tool=%s, fields=%s, requires_inference=%s",
                canonical_workload, next_tool, list(canonical_fields.keys()), requires_inference)
    return result
