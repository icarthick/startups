"""cluster_terraform — classify, build edges, compute depth, and cluster GCP resources.

Takes a flat list of extracted Terraform resources and produces classified,
depth-assigned, clustered output ready for gcp-resource-inventory.json and
gcp-resource-clusters.json.
"""

import logging
import re
from collections import defaultdict, deque
from typing import Any

logger = logging.getLogger("migration_knowledge.cluster_terraform")


def _match_pattern(resource_type: str, pattern: str) -> bool:
    """Match a resource type against a pattern (supports trailing *)."""
    if pattern.endswith("*"):
        return resource_type.startswith(pattern[:-1])
    return resource_type == pattern


# ─── CLASSIFY ─────────────────────────────────────────────────────────────────

def _classify(resources: list[dict], knowledge: dict) -> list[dict]:
    """Classify resources as excluded, PRIMARY, or SECONDARY."""
    # Load classification knowledge
    excluded = []
    for key, data in knowledge.items():
        if data.get("kind") == "excluded-types":
            excluded = data.get("entries", [])
    primary_map = {}
    for key, data in knowledge.items():
        if data.get("kind") == "primary-types":
            for e in data.get("entries", []):
                primary_map[e["type"]] = e["tier"]
    secondary_entries = []
    for key, data in knowledge.items():
        if data.get("kind") == "secondary-patterns":
            secondary_entries = data.get("entries", [])

    classified = []
    for res in resources:
        res_type = res.get("type", "")

        # Priority 0: excluded
        is_excluded = any(_match_pattern(res_type, e["pattern"]) for e in excluded)
        if is_excluded:
            logger.debug("  excluded: %s", res.get("address"))
            continue

        # Priority 1: PRIMARY
        if res_type in primary_map:
            res["classification"] = "PRIMARY"
            res["tier"] = primary_map[res_type]
            res["confidence"] = 0.99
            classified.append(res)
            continue

        # Priority 2: SECONDARY by pattern
        matched_role = None
        for entry in secondary_entries:
            if _match_pattern(res_type, entry["pattern"]):
                matched_role = entry["role"]
                break

        res["classification"] = "SECONDARY"
        res["secondary_role"] = matched_role or "configuration"
        res["confidence"] = 0.99 if matched_role else 0.5
        classified.append(res)

    return classified


# ─── EDGES + SERVES ───────────────────────────────────────────────────────────

def _build_edges(resources: list[dict]) -> list[dict]:
    """Build dependency edges from depends_on and config references."""
    address_set = {r["address"] for r in resources}
    edges = []

    for res in resources:
        # Explicit depends_on
        for dep in res.get("depends_on", []):
            if dep in address_set:
                edges.append({"from": res["address"], "to": dep, "type": "depends_on"})

        # Scan config for resource references (google_X.name patterns)
        config_str = str(res.get("config", {}))
        refs = re.findall(r"(google_\w+\.\w+)", config_str)
        for ref in refs:
            if ref in address_set and ref != res["address"]:
                edges.append({"from": res["address"], "to": ref, "type": "reference"})

    # Populate serves for SECONDARY resources
    primary_addresses = {r["address"] for r in resources if r.get("classification") == "PRIMARY"}
    for res in resources:
        if res.get("classification") == "SECONDARY":
            serves = set()
            for edge in edges:
                if edge["from"] == res["address"] and edge["to"] in primary_addresses:
                    serves.add(edge["to"])
            res["serves"] = sorted(serves)

    return edges


# ─── DEPTH (Kahn's algorithm) ─────────────────────────────────────────────────

def _compute_depth(resources: list[dict], edges: list[dict]) -> None:
    """Assign topological depth using Kahn's algorithm."""
    address_to_res = {r["address"]: r for r in resources}
    in_degree = defaultdict(int)
    dependents = defaultdict(list)

    for r in resources:
        in_degree[r["address"]] = 0

    for edge in edges:
        if edge["to"] in address_to_res and edge["from"] in address_to_res:
            in_degree[edge["from"]] += 1
            dependents[edge["to"]].append(edge["from"])

    # BFS from nodes with in_degree 0
    queue = deque()
    for addr, degree in in_degree.items():
        if degree == 0:
            queue.append(addr)
            address_to_res[addr]["depth"] = 0

    while queue:
        current = queue.popleft()
        current_depth = address_to_res[current]["depth"]
        for dep in dependents[current]:
            in_degree[dep] -= 1
            new_depth = current_depth + 1
            if "depth" not in address_to_res[dep] or new_depth > address_to_res[dep]["depth"]:
                address_to_res[dep]["depth"] = new_depth
            if in_degree[dep] == 0:
                queue.append(dep)

    # Any remaining without depth (cycles) get max_depth + 1
    max_depth = max((r.get("depth", 0) for r in resources), default=0)
    for r in resources:
        if "depth" not in r:
            r["depth"] = max_depth + 1


# ─── CLUSTERING ───────────────────────────────────────────────────────────────

def _cluster(resources: list[dict], edges: list[dict]) -> list[dict]:
    """Apply clustering rules. Returns cluster list."""
    primaries = [r for r in resources if r.get("classification") == "PRIMARY"]
    secondaries = [r for r in resources if r.get("classification") == "SECONDARY"]

    clusters = []
    assigned = set()
    region_counters = defaultdict(lambda: defaultdict(int))

    def make_cluster_id(tier, res_type, region):
        """Generate deterministic cluster ID."""
        service = res_type.replace("google_", "").split("_")[0]
        region_counters[tier][f"{service}_{region}"] += 1
        seq = region_counters[tier][f"{service}_{region}"]
        return f"{tier}_{service}_{region}_{seq:03d}"

    # Rule 1: Networking cluster — group all networking primaries together
    net_primaries = [r for r in primaries if r.get("tier") == "networking"]
    if net_primaries:
        net_addresses = {r["address"] for r in net_primaries}
        net_secondaries = [r for r in secondaries if r.get("secondary_role") == "network_path"]
        all_net = net_primaries + net_secondaries
        for r in all_net:
            assigned.add(r["address"])

        region = "global"
        cluster_id = f"networking_vpc_{region}_001"
        for r in all_net:
            r["cluster_id"] = cluster_id

        clusters.append({
            "cluster_id": cluster_id,
            "gcp_region": region,
            "primary_resources": [r["address"] for r in net_primaries],
            "secondary_resources": [r["address"] for r in net_secondaries],
            "creation_order_depth": min(r.get("depth", 0) for r in net_primaries),
        })

    # Rule 2: Same-type grouping for remaining primaries
    type_groups = defaultdict(list)
    for r in primaries:
        if r["address"] not in assigned:
            type_groups[r["type"]].append(r)

    for res_type, group in type_groups.items():
        # Find secondaries that serve any resource in this group
        group_addresses = {r["address"] for r in group}
        group_secondaries = [
            r for r in secondaries
            if r["address"] not in assigned
            and any(s in group_addresses for s in r.get("serves", []))
        ]

        tier = group[0].get("tier", "other")
        region = "us-central1"  # default; could extract from config
        cluster_id = make_cluster_id(tier, res_type, region)

        for r in group + group_secondaries:
            r["cluster_id"] = cluster_id
            assigned.add(r["address"])

        clusters.append({
            "cluster_id": cluster_id,
            "gcp_region": region,
            "primary_resources": [r["address"] for r in group],
            "secondary_resources": [r["address"] for r in group_secondaries],
            "creation_order_depth": min(r.get("depth", 0) for r in group),
        })

    # Assign any remaining unassigned secondaries to nearest cluster
    for r in secondaries:
        if r["address"] not in assigned:
            # Attach to first cluster that contains a resource it serves
            placed = False
            for cl in clusters:
                if any(s in cl["primary_resources"] for s in r.get("serves", [])):
                    cl["secondary_resources"].append(r["address"])
                    r["cluster_id"] = cl["cluster_id"]
                    placed = True
                    break
            if not placed and clusters:
                # Fallback: attach to last cluster
                clusters[-1]["secondary_resources"].append(r["address"])
                r["cluster_id"] = clusters[-1]["cluster_id"]

    # Sort clusters by creation_order_depth
    clusters.sort(key=lambda c: c["creation_order_depth"])

    return clusters


# ─── Main entry point ─────────────────────────────────────────────────────────

def cluster_terraform(
    resources: list[dict],
    migration_dir: str | None = None,
    ai_detection: dict | None = None,
    metadata: dict | None = None,
    knowledge: dict[str, Any] = None,
) -> dict:
    """Classify, build edges, compute depth, cluster, and optionally write output files.

    Args:
        resources: Flat list from LLM's Terraform parsing. Each resource needs
            at minimum: address, type, name, config, depends_on.
        migration_dir: If provided, writes gcp-resource-inventory.json and
            gcp-resource-clusters.json to this directory.
        ai_detection: Output from detect_ai_signals (included in inventory file).
        metadata: Report metadata (report_date, project_directory, terraform_version).
        knowledge: Pre-loaded knowledge store.

    Returns:
        {
            "resources": [...],
            "clusters": [...],
            "summary": {...},
            "files_written": [...] (if migration_dir provided)
        }
    """
    logger.info(">>> cluster_terraform called: %d resources, migration_dir=%s", len(resources), migration_dir)

    total_input = len(resources)

    # Classify
    classified = _classify(resources, knowledge)
    excluded_count = total_input - len(classified)
    primary_count = sum(1 for r in classified if r.get("classification") == "PRIMARY")
    secondary_count = sum(1 for r in classified if r.get("classification") == "SECONDARY")
    logger.info("  classified: %d primary, %d secondary, %d excluded", primary_count, secondary_count, excluded_count)

    # Build edges
    edges = _build_edges(classified)
    logger.info("  edges: %d", len(edges))

    # Compute depth
    _compute_depth(classified, edges)

    # Cluster
    clusters = _cluster(classified, edges)
    logger.info("  clusters: %d", len(clusters))

    summary = {
        "total_resources": len(classified),
        "primary_resources": primary_count,
        "secondary_resources": secondary_count,
        "excluded_resources": excluded_count,
        "total_clusters": len(clusters),
        "classification_coverage": "100%",
    }

    result = {
        "resources": classified,
        "clusters": clusters,
        "summary": summary,
    }

    # Write files if migration_dir provided
    if migration_dir:
        import json
        from pathlib import Path
        out_dir = Path(migration_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        # gcp-resource-inventory.json
        inventory = {
            "metadata": metadata or {"report_date": "", "project_directory": ""},
            "summary": summary,
            "resources": classified,
            "ai_detection": ai_detection or {"has_ai_workload": False, "confidence": 0, "confidence_level": "none", "signals_found": [], "ai_services": []},
        }
        inventory_path = out_dir / "gcp-resource-inventory.json"
        inventory_path.write_text(json.dumps(inventory, indent=2) + "\n")

        # gcp-resource-clusters.json
        clusters_output = {"clusters": clusters}
        clusters_path = out_dir / "gcp-resource-clusters.json"
        clusters_path.write_text(json.dumps(clusters_output, indent=2) + "\n")

        result["files_written"] = ["gcp-resource-inventory.json", "gcp-resource-clusters.json"]
        logger.info("  wrote: %s", result["files_written"])

    logger.info("<<< cluster_terraform: %d resources → %d clusters", len(classified), len(clusters))
    return result
