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

def _build_edges(resources: list[dict], external_edges: list[dict] | None = None) -> list[dict]:
    """Build dependency edges from external scanner, depends_on, and config references.

    Populates serves bidirectionally and transitively via IAM bridge pattern.
    """
    address_set = {r["address"] for r in resources}
    edges = []
    seen = set()

    def _add(frm, to, edge_type):
        key = (frm, to)
        if key not in seen and frm in address_set and to in address_set:
            edges.append({"from": frm, "to": to, "type": edge_type})
            seen.add(key)

    # External edges (from scanner — highest quality)
    for edge in (external_edges or []):
        _add(edge["from"], edge["to"], edge.get("type", "reference"))

    # Explicit depends_on
    for res in resources:
        for dep in res.get("depends_on", []):
            _add(res["address"], dep, "depends_on")

    # Config string scan (fallback for edges not in scanner or depends_on)
    for res in resources:
        config_str = str(res.get("config", {}))
        refs = re.findall(r"(google_\w+\.\w+)", config_str)
        for ref in refs:
            if ref != res["address"]:
                _add(res["address"], ref, "config_scan")

    # Populate serves — BIDIRECTIONAL
    primary_addresses = {r["address"] for r in resources if r.get("classification") == "PRIMARY"}
    for res in resources:
        if res.get("classification") == "SECONDARY":
            serves = set()
            for edge in edges:
                # Outgoing: secondary → primary
                if edge["from"] == res["address"] and edge["to"] in primary_addresses:
                    serves.add(edge["to"])
                # Incoming: primary → secondary (bidirectional)
                if edge["to"] == res["address"] and edge["from"] in primary_addresses:
                    serves.add(edge["from"])
            res["serves"] = sorted(serves)

    # Transitive bridge: access_control links identity/encryption to primaries
    access_control = {r["address"] for r in resources if r.get("secondary_role") == "access_control"}
    identity_or_encryption = {r["address"] for r in resources
                              if r.get("secondary_role") in ("identity", "encryption")}

    for ac_addr in access_control:
        # Collect all neighbors of this bridge node
        neighbors = set()
        for edge in edges:
            if edge["from"] == ac_addr:
                neighbors.add(edge["to"])
            if edge["to"] == ac_addr:
                neighbors.add(edge["from"])

        linked_primaries = neighbors & primary_addresses
        linked_identities = neighbors & identity_or_encryption

        # Propagate: each linked identity/encryption now serves each linked primary
        if linked_primaries and linked_identities:
            for id_addr in linked_identities:
                id_res = next((r for r in resources if r["address"] == id_addr), None)
                if id_res:
                    current = set(id_res.get("serves", []))
                    current.update(linked_primaries)
                    id_res["serves"] = sorted(current)

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

def _cluster(resources: list[dict], edges: list[dict], file_map: dict[str, str] | None = None) -> list[dict]:
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

    # Shared infra types — always shared unless they have a specific serves
    _SHARED_INFRA_PREFIXES = ("google_monitoring_", "google_logging_", "google_project_service", "random_")

    def _is_shared_infra(res):
        return (any(res["type"].startswith(p) for p in _SHARED_INFRA_PREFIXES)
                and not res.get("serves"))

    # Rule 1: Networking cluster — group all networking primaries together
    net_primaries = [r for r in primaries if r.get("tier") == "networking"]
    if net_primaries:
        net_secondaries = [r for r in secondaries if r.get("secondary_role") == "network_path"]
        all_net = net_primaries + net_secondaries
        for r in all_net:
            assigned.add(r["address"])

        cluster_id = "networking_vpc_global_001"
        for r in all_net:
            r["cluster_id"] = cluster_id

        clusters.append({
            "cluster_id": cluster_id,
            "gcp_region": "global",
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
        group_addresses = {r["address"] for r in group}
        group_secondaries = [
            r for r in secondaries
            if r["address"] not in assigned
            and any(s in group_addresses for s in r.get("serves", []))
        ]

        tier = group[0].get("tier", "other")
        region = "us-central1"
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

    # Rule 3: Assign remaining secondaries — serves, file proximity, then shared-infra
    shared_infra_secondaries = []
    for r in secondaries:
        if r["address"] in assigned:
            continue

        # 3a: Attach via serves
        placed = False
        for cl in clusters:
            if any(s in cl["primary_resources"] for s in r.get("serves", [])):
                cl["secondary_resources"].append(r["address"])
                r["cluster_id"] = cl["cluster_id"]
                assigned.add(r["address"])
                placed = True
                break
        if placed:
            continue

        # 3b: File proximity — same .tf file as a primary in a cluster
        if file_map and r["address"] in file_map:
            res_file = file_map[r["address"]]
            for cl in clusters:
                if any(file_map.get(p) == res_file for p in cl["primary_resources"]):
                    cl["secondary_resources"].append(r["address"])
                    r["cluster_id"] = cl["cluster_id"]
                    assigned.add(r["address"])
                    placed = True
                    break
        if placed:
            continue

        # 3c: Shared infrastructure or final fallback
        shared_infra_secondaries.append(r)
        assigned.add(r["address"])

    # Create shared infrastructure cluster for all remaining
    if shared_infra_secondaries:
        cluster_id = "shared_infrastructure_global_001"
        for r in shared_infra_secondaries:
            r["cluster_id"] = cluster_id
        clusters.append({
            "cluster_id": cluster_id,
            "gcp_region": "global",
            "primary_resources": [],
            "secondary_resources": [r["address"] for r in shared_infra_secondaries],
            "creation_order_depth": 0,
        })

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
    edges: list[dict] | None = None,
    file_map: dict[str, str] | None = None,
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
    computed_edges = _build_edges(classified, external_edges=edges)
    logger.info("  edges: %d", len(computed_edges))

    # Compute depth
    _compute_depth(classified, computed_edges)

    # Cluster
    clusters = _cluster(classified, computed_edges, file_map=file_map)
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
