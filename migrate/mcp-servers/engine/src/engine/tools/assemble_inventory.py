"""Assemble heroku-resource-inventory.json from intermediate discovery files.

Reads _terraform-discovery.json and _billing-discovery.json, merges them
into the final inventory artifact.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("engine.assemble_inventory")

REQUIRED_FIELDS = {"resource_id", "resource_type", "heroku_app", "config"}
FORBIDDEN_FIELDS = {"cluster_id", "creation_order_depth", "edges", "dependencies", "must_migrate_together"}


def assemble_heroku_inventory(migration_dir: str) -> dict[str, Any]:
    """Assemble heroku-resource-inventory.json from intermediate files.

    Args:
        migration_dir: Path to migration run directory.

    Returns:
        Dict with status and inventory summary.
    """
    mdir = Path(migration_dir)
    tf_path = mdir / "_terraform-discovery.json"
    billing_path = mdir / "_billing-discovery.json"

    tf_data = None
    billing_data = None

    if tf_path.exists():
        with open(tf_path) as f:
            tf_data = json.load(f)
    if billing_path.exists():
        with open(billing_path) as f:
            billing_data = json.load(f)

    if not tf_data and not billing_data:
        return {"status": "error", "reason": "No discovery data available. Neither _terraform-discovery.json nor _billing-discovery.json found."}

    # Assemble
    resources = tf_data.get("resources", []) if tf_data else []
    apps = tf_data.get("apps", []) if tf_data else []
    terraform_metadata = tf_data.get("terraform_metadata") if tf_data else None

    # Discovery sources
    sources = tf_data.get("metadata", {}).get("discovery_sources", []) if tf_data else []
    if billing_data and "billing" not in sources:
        sources.append("billing")

    # Confidence
    confidence = "full"
    if tf_data and tf_data.get("terraform_metadata", {}).get("parse_warnings"):
        confidence = "reduced"

    # Billing profile
    billing_profile = None
    if billing_data:
        billing_profile = billing_data.get("billing_profile", {"available": False})
    else:
        billing_profile = {"available": False}

    # Validate resources
    validation_errors = []
    for i, r in enumerate(resources):
        missing = REQUIRED_FIELDS - set(r.keys())
        if missing:
            validation_errors.append(f"Resource [{i}] missing fields: {missing}")
        forbidden = FORBIDDEN_FIELDS & set(r.keys())
        if forbidden:
            validation_errors.append(f"Resource [{i}] has forbidden fields: {forbidden}")

    # Build inventory
    inventory = {
        "metadata": {
            "discovery_timestamp": datetime.now(timezone.utc).isoformat(),
            "total_apps_discovered": len(apps),
            "discovery_sources": sources,
            "confidence": confidence,
        },
        "resources": resources,
        "apps": apps,
        "billing_profile": billing_profile,
    }

    if terraform_metadata:
        inventory["terraform_metadata"] = terraform_metadata

    # Write
    out_path = mdir / "heroku-resource-inventory.json"
    with open(out_path, "w") as f:
        json.dump(inventory, f, indent=2)

    logger.info("Assembled inventory: %d resources, %d apps, billing=%s",
                len(resources), len(apps), billing_profile.get("available", False))

    return {
        "status": "ok",
        "summary": {
            "total_resources": len(resources),
            "total_apps": len(apps),
            "discovery_sources": sources,
            "billing_available": billing_profile.get("available", False),
            "confidence": confidence,
            "validation_errors": validation_errors,
        },
    }
