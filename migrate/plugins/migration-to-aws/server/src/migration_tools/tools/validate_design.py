"""validate_design — validates aws-design.json against the output checklist.

Runs the 12 structural assertions on the design artifact. Returns pass/fail
with specific violations. Called after Step 2 completes, before the handoff gate.
"""

import json
import logging
from typing import Any

logger = logging.getLogger("migration_tools.validate_design")


def validate_design(
    design: dict,
    clusters_source: dict | None = None,
    knowledge: dict[str, Any] = None,
) -> dict:
    """Validate aws-design.json against the output checklist.

    Args:
        design: The aws-design.json content as a dict.
        clusters_source: The gcp-resource-clusters.json content (for cluster_id cross-check).
        knowledge: Pre-loaded knowledge store (for deferred-mappings prefix check).

    Returns:
        {"valid": true/false, "violations": [...], "checks_passed": N, "checks_total": N}
    """
    logger.info(">>> validate_design called")
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
            logger.warning("  FAIL: %s", message)

    # 1. clusters array is non-empty
    clusters = design.get("clusters", [])
    check(len(clusters) > 0, "clusters array is empty")

    # 2. Every cluster has cluster_id, gcp_region, aws_region
    for i, cluster in enumerate(clusters):
        check("cluster_id" in cluster, f"clusters[{i}] missing cluster_id")
        check("gcp_region" in cluster, f"clusters[{i}] missing gcp_region")
        check("aws_region" in cluster, f"clusters[{i}] missing aws_region")

    # 3. Cross-check cluster_ids against source clusters
    if clusters_source:
        source_ids = {c.get("cluster_id") for c in clusters_source.get("clusters", [])}
        for i, cluster in enumerate(clusters):
            cid = cluster.get("cluster_id", "")
            check(cid in source_ids, f"clusters[{i}].cluster_id '{cid}' not found in gcp-resource-clusters.json")

    # 4-11. Per-resource checks
    all_addresses = []
    deferred_prefixes = []

    # Load deferred prefixes from knowledge
    if knowledge:
        for key, data in knowledge.items():
            if data.get("kind") == "deferred-mappings":
                for entry in data.get("entries", []):
                    deferred_prefixes.append(entry.get("prefix", ""))

    for i, cluster in enumerate(clusters):
        resources = cluster.get("resources", [])
        for j, resource in enumerate(resources):
            path = f"clusters[{i}].resources[{j}]"
            gcp_type = resource.get("gcp_type", "")
            aws_service = resource.get("aws_service", "")

            # Required fields
            check("gcp_address" in resource, f"{path} missing gcp_address")
            check("gcp_type" in resource, f"{path} missing gcp_type")
            check("aws_service" in resource, f"{path} missing aws_service")
            check("aws_config" in resource, f"{path} missing aws_config")
            check("human_expertise_required" in resource, f"{path} missing human_expertise_required")

            # Confidence enum
            confidence = resource.get("confidence", "")
            check(confidence in ("deterministic", "inferred", "billing_inferred"),
                  f"{path} confidence='{confidence}' not in valid enum")

            # Rationale non-empty
            check(bool(resource.get("rationale")), f"{path} rationale is empty or missing")

            # Deferred resources: BigQuery gate
            is_deferred = any(gcp_type.startswith(p) for p in deferred_prefixes)
            if is_deferred:
                check(aws_service == "Deferred — specialist engagement",
                      f"{path} {gcp_type} must be 'Deferred — specialist engagement', got '{aws_service}'")
                check(resource.get("human_expertise_required") is True,
                      f"{path} {gcp_type} must have human_expertise_required=true")

            # Cloud SQL: correct family per availability
            if gcp_type == "google_sql_database_instance" and not is_deferred:
                valid_services = {"RDS PostgreSQL", "RDS MySQL", "Aurora PostgreSQL", "Aurora MySQL", "RDS SQL Server"}
                check(aws_service in valid_services,
                      f"{path} sql_database_instance aws_service='{aws_service}' not in valid set")

            # Track addresses for uniqueness
            addr = resource.get("gcp_address", "")
            all_addresses.append(addr)

    # No duplicate gcp_address
    seen = set()
    for addr in all_addresses:
        check(addr not in seen, f"Duplicate gcp_address: '{addr}'")
        seen.add(addr)

    valid = len(violations) == 0
    logger.info("<<< validate_design: valid=%s, passed=%d/%d, violations=%d",
                valid, checks_passed, checks_total, len(violations))

    return {
        "valid": valid,
        "checks_passed": checks_passed,
        "checks_total": checks_total,
        "violations": violations,
    }
