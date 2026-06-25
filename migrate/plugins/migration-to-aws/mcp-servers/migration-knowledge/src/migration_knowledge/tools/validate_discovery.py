"""validate_discovery — validates discovery phase output artifacts.

Checks structural correctness of gcp-resource-inventory.json,
gcp-resource-clusters.json, ai-workload-profile.json, and billing-profile.json.
"""

import logging
from typing import Any

logger = logging.getLogger("migration_knowledge.validate_discovery")

VALID_CLASSIFICATIONS = {"PRIMARY", "SECONDARY"}
VALID_TIERS = {"compute", "database", "storage", "networking", "identity", "messaging", "monitoring"}
RESOURCE_REQUIRED_FIELDS = {"address", "type", "name", "classification", "tier", "confidence", "config", "depth", "cluster_id"}
CLUSTER_REQUIRED_FIELDS = {"cluster_id", "gcp_region", "primary_resources", "secondary_resources", "creation_order_depth"}


def validate_discovery(
    artifact_type: str,
    content: dict,
) -> dict:
    """Validate a discovery artifact against its schema.

    Args:
        artifact_type: One of "iac", "ai-profile", "billing".
        content: The artifact content as a dict.
            For "iac": pass {"inventory": <inventory>, "clusters": <clusters>}.
            For "ai-profile": pass the ai-workload-profile.json content.
            For "billing": pass the billing-profile.json content.

    Returns:
        {"valid": true/false, "violations": [...], "checks_passed": N, "checks_total": N}
    """
    logger.info(">>> validate_discovery called: type=%s", artifact_type)

    validators = {
        "iac": _validate_iac,
        "ai-profile": _validate_ai_profile,
        "billing": _validate_billing,
    }

    validator = validators.get(artifact_type)
    if not validator:
        return {"valid": False, "violations": [f"Unknown artifact_type: '{artifact_type}'. Valid: {list(validators.keys())}"], "checks_passed": 0, "checks_total": 0}

    violations = []
    checks_passed = 0
    checks_total = 0

    def check(condition: bool, message: str):
        nonlocal checks_passed, checks_total
        checks_total += 1
        if condition:
            checks_passed += 1
        else:
            violations.append(message)

    validator(content, check)

    valid = len(violations) == 0
    logger.info("<<< validate_discovery: valid=%s, passed=%d/%d", valid, checks_passed, checks_total)
    return {"valid": valid, "violations": violations, "checks_passed": checks_passed, "checks_total": checks_total}


def _validate_iac(content: dict, check):
    """Validate gcp-resource-inventory.json + gcp-resource-clusters.json."""
    inventory = content.get("inventory", {})
    clusters = content.get("clusters", {})

    # --- Inventory checks ---
    check("metadata" in inventory, "inventory: missing 'metadata'")
    check("summary" in inventory, "inventory: missing 'summary'")
    resources = inventory.get("resources", [])
    check(len(resources) > 0, "inventory: 'resources' array is empty")

    # Check summary fields
    summary = inventory.get("summary", {})
    check("total_resources" in summary, "inventory: summary missing 'total_resources'")
    check("primary_resources" in summary, "inventory: summary missing 'primary_resources'")
    check("total_clusters" in summary, "inventory: summary missing 'total_clusters'")

    # Check each resource has required fields
    for i, res in enumerate(resources[:20]):  # cap at 20 to avoid huge output
        for field in RESOURCE_REQUIRED_FIELDS:
            check(field in res, f"inventory: resources[{i}] ('{res.get('address', '?')}') missing '{field}'")

        if "classification" in res:
            check(res["classification"] in VALID_CLASSIFICATIONS,
                  f"inventory: resources[{i}] classification='{res.get('classification')}' not in {VALID_CLASSIFICATIONS}")
        if "tier" in res:
            check(res["tier"] in VALID_TIERS,
                  f"inventory: resources[{i}] tier='{res.get('tier')}' not in {VALID_TIERS}")

    # --- Clusters checks ---
    cluster_list = clusters.get("clusters", [])
    check(len(cluster_list) > 0, "clusters: 'clusters' array is empty")

    for i, cl in enumerate(cluster_list):
        for field in CLUSTER_REQUIRED_FIELDS:
            check(field in cl, f"clusters[{i}] ('{cl.get('cluster_id', '?')}') missing '{field}'")

    # Cross-reference: cluster_ids in inventory must match clusters file
    inventory_cluster_ids = {r.get("cluster_id") for r in resources if r.get("cluster_id")}
    cluster_file_ids = {cl.get("cluster_id") for cl in cluster_list}
    for cid in inventory_cluster_ids:
        check(cid in cluster_file_ids,
              f"inventory references cluster_id '{cid}' not found in clusters file")


def _validate_ai_profile(content: dict, check):
    """Validate ai-workload-profile.json."""
    check("metadata" in content, "ai-profile: missing 'metadata'")
    check("summary" in content, "ai-profile: missing 'summary'")

    summary = content.get("summary", {})
    check("ai_source" in summary, "ai-profile: summary missing 'ai_source'")
    check("overall_confidence" in summary, "ai-profile: summary missing 'overall_confidence'")

    metadata = content.get("metadata", {})
    check("profile_source" in metadata, "ai-profile: metadata missing 'profile_source'")


def _validate_billing(content: dict, check):
    """Validate billing-profile.json."""
    check("summary" in content, "billing: missing 'summary'")
    check("services" in content, "billing: missing 'services'")

    summary = content.get("summary", {})
    check("total_monthly_spend" in summary, "billing: summary missing 'total_monthly_spend'")

    services = content.get("services", [])
    check(len(services) > 0, "billing: 'services' array is empty")

    for i, svc in enumerate(services[:10]):
        check("gcp_service" in svc, f"billing: services[{i}] missing 'gcp_service'")
        check("monthly_cost" in svc, f"billing: services[{i}] missing 'monthly_cost'")
