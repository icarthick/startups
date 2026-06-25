"""Extract billing summary from GCP billing export files.

Parses CSV/JSON billing exports, aggregates service-level costs,
detects CUD commitments/discounts, flags AI signals, and writes
billing-profile.json.
"""

import csv
import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Any

logger = logging.getLogger("migration_orchestrator.extract_billing")

# GCP service name → Terraform resource type mapping
SERVICE_TO_TF_TYPE = {
    "Cloud Run": "google_cloud_run_service",
    "Cloud SQL": "google_sql_database_instance",
    "Compute Engine": "google_compute_instance",
    "Cloud Storage": "google_storage_bucket",
    "Cloud Functions": "google_cloudfunctions_function",
    "Cloud Pub/Sub": "google_pubsub_topic",
    "Cloud Memorystore": "google_redis_instance",
    "Kubernetes Engine": "google_container_cluster",
    "Cloud Load Balancing": "google_compute_forwarding_rule",
    "Vertex AI": "google_vertex_ai_endpoint",
    "BigQuery": "google_bigquery_dataset",
    "Cloud Spanner": "google_spanner_instance",
    "Firestore": "google_firestore_database",
    "Cloud Tasks": "google_cloud_tasks_queue",
    "Cloud Scheduler": "google_cloud_scheduler_job",
    "Secret Manager": "google_secret_manager_secret",
    "Cloud NAT": "google_compute_router_nat",
    "VPC Network": "google_compute_network",
    "Cloud DNS": "google_dns_managed_zone",
    "Cloud Armor": "google_compute_security_policy",
    "Artifact Registry": "google_artifact_registry_repository",
}

# AI signal patterns matched against SKU descriptions
AI_PATTERNS = [
    ("vertex_ai", re.compile(r"Vertex AI|AI Platform", re.IGNORECASE)),
    ("bigquery_ml", re.compile(r"BigQuery ML", re.IGNORECASE)),
    ("generative_ai", re.compile(r"Generative AI|Gemini|foundation model", re.IGNORECASE)),
    ("specialized_ai", re.compile(r"Document AI|Vision AI|Speech-to-Text|Natural Language API|Cloud Translation|Dialogflow", re.IGNORECASE)),
]

# Commitment detection patterns
CUD_FEE_PATTERN = re.compile(r"Commitment v1:|Commitment - dollar based", re.IGNORECASE)
CUD_TERM_PATTERN = re.compile(r"(\d+)\s*Year", re.IGNORECASE)


def _find_billing_file(project_dir: str) -> Path | None:
    """Find first matching billing file in project directory."""
    patterns = [
        "*billing*.csv", "*billing*.json",
        "*cost*.csv", "*cost*.json",
        "*usage*.csv", "*usage*.json",
    ]
    root = Path(project_dir)
    for pattern in patterns:
        matches = list(root.rglob(pattern))
        if matches:
            return matches[0]
    return None


def _parse_csv(path: Path) -> list[dict]:
    """Parse GCP billing export CSV into line items."""
    items = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Normalize field names (GCP exports vary)
            item = {}
            for k, v in row.items():
                key = k.strip().lower().replace(" ", "_")
                item[key] = v.strip() if v else ""
            items.append(item)
    return items


def _parse_json(path: Path) -> list[dict]:
    """Parse BigQuery billing export JSON into line items."""
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "rows" in data:
        return data["rows"]
    return []


def _get_cost(item: dict) -> float:
    """Extract cost from a line item, preferring list price."""
    for field in ["costatlistusd", "cost_at_list_usd", "costAtListUSD", "cost"]:
        key = field.lower().replace(" ", "_")
        if key in item:
            try:
                return float(item[key])
            except (ValueError, TypeError):
                continue
    return 0.0


def _get_field(item: dict, *candidates: str) -> str:
    """Get field value trying multiple candidate names."""
    for c in candidates:
        key = c.lower().replace(" ", "_")
        if key in item and item[key]:
            return item[key]
    return ""


def _is_commitment_fee(item: dict) -> bool:
    """Check if a line item is a CUD commitment fee row."""
    sku = _get_field(item, "sku_description", "sku.description", "skuDescription")
    resource = _get_field(item, "resource_global_name", "resourceGlobalName", "resource_name", "resourceName")
    if CUD_FEE_PATTERN.search(sku):
        return True
    if "project_commitments" in resource or resource.startswith("commitment-"):
        return True
    return False


def _extract_discount_credits(items: list[dict]) -> dict:
    """Sum discount credit columns across all items."""
    credits = {
        "committed_usage_discount": 0.0,
        "sustained_usage_discount": 0.0,
        "free_tier": 0.0,
    }
    credit_fields = {
        "committed_usage_discount": ["committedusagediscount", "committed_usage_discount", "committedusagediscountdollarbase"],
        "sustained_usage_discount": ["sustainedusagediscount", "sustained_usage_discount"],
        "free_tier": ["freetier", "free_tier"],
    }
    for item in items:
        for credit_type, fields in credit_fields.items():
            for field in fields:
                key = field.lower().replace(" ", "_")
                if key in item:
                    try:
                        val = float(item[key])
                        if val != 0:
                            credits[credit_type] += val
                    except (ValueError, TypeError):
                        pass
    return credits


def extract_billing_summary(project_dir: str, output_dir: str | None = None) -> dict[str, Any]:
    """Extract billing summary from GCP billing export.

    Scans for billing files, parses CSV/JSON, aggregates service costs,
    detects CUD commitments, flags AI signals, and optionally writes
    billing-profile.json.

    Args:
        project_dir: Path to the project root (scanned for billing files).
        output_dir: If provided, writes billing-profile.json here.

    Returns:
        Dict with billing profile or error/skip status.
    """
    # Step 0: Find billing file
    billing_file = _find_billing_file(project_dir)
    if not billing_file:
        return {"status": "skipped", "reason": "No billing files found"}

    logger.info("Found billing file: %s", billing_file)

    # Step 1: Parse
    if billing_file.suffix == ".csv":
        items = _parse_csv(billing_file)
    else:
        items = _parse_json(billing_file)

    if not items:
        return {"status": "skipped", "reason": f"Billing file empty: {billing_file.name}"}

    # Step 1.5: Identify commitments
    commitment_fees = [i for i in items if _is_commitment_fee(i)]
    non_commitment_items = [i for i in items if not _is_commitment_fee(i)]

    commitment_details = []
    total_commitment_fees = 0.0
    for fee_item in commitment_fees:
        sku = _get_field(fee_item, "sku_description", "sku.description", "skuDescription")
        cost = _get_cost(fee_item)
        total_commitment_fees += cost
        term_match = CUD_TERM_PATTERN.search(sku)
        term = f"{term_match.group(1)}_year" if term_match else "unknown"
        cud_type = "dollar_based" if "dollar based" in sku.lower() else "resource_based"
        region = _get_field(fee_item, "region", "location.region")
        commitment_details.append({
            "type": cud_type,
            "term": term,
            "covered_services": [_get_field(fee_item, "service_description", "service.description", "serviceDescription")],
            "region": region,
            "monthly_fee": round(cost, 2),
            "sku_description": sku,
        })

    discount_credits = _extract_discount_credits(items)
    total_cud_credits = discount_credits["committed_usage_discount"]

    # Step 2: Build service profile
    services_map: dict[str, dict] = {}
    for item in non_commitment_items:
        service = _get_field(item, "service_description", "service.description", "serviceDescription")
        if not service:
            continue
        cost = _get_cost(item)
        sku = _get_field(item, "sku_description", "sku.description", "skuDescription")

        if service not in services_map:
            services_map[service] = {"cost": 0.0, "skus": {}, "ai_signals": set()}
        services_map[service]["cost"] += cost
        if sku:
            services_map[service]["skus"][sku] = services_map[service]["skus"].get(sku, 0.0) + cost

    total_spend = sum(s["cost"] for s in services_map.values())

    # Step 3: AI signals
    all_ai_services = set()
    for service, data in services_map.items():
        for sku_desc in data["skus"]:
            for signal_name, pattern in AI_PATTERNS:
                if pattern.search(sku_desc) or pattern.search(service):
                    data["ai_signals"].add(signal_name)
                    all_ai_services.add(service)

    # Build services list (sorted by cost descending)
    services_list = []
    for service, data in sorted(services_map.items(), key=lambda x: x[1]["cost"], reverse=True):
        if data["cost"] <= 0:
            continue
        top_skus = sorted(data["skus"].items(), key=lambda x: x[1], reverse=True)[:5]
        services_list.append({
            "gcp_service": service,
            "gcp_service_type": SERVICE_TO_TF_TYPE.get(service, ""),
            "monthly_cost": round(data["cost"], 2),
            "percentage_of_total": round(data["cost"] / total_spend, 2) if total_spend > 0 else 0,
            "top_skus": [{"sku_description": s, "monthly_cost": round(c, 2)} for s, c in top_skus],
            "ai_signals": sorted(data["ai_signals"]),
        })

    # Cost basis
    has_cuds = bool(commitment_fees) or total_cud_credits != 0
    total_discounts = sum(discount_credits.values())
    total_net = total_spend + total_discounts  # discounts are negative
    effective_discount = round((total_spend - total_net) / total_spend * 100, 1) if total_spend > 0 and total_discounts < 0 else 0.0

    # AI confidence
    ai_detected = bool(all_ai_services)
    ai_confidence = 0.0
    if ai_detected:
        # Higher confidence for Vertex/Generative AI, lower for just BigQuery ML
        ai_confidence = 0.95 if any(s in str(all_ai_services) for s in ["Vertex", "Generative"]) else 0.80

    # Step 4: Assemble profile
    profile = {
        "metadata": {
            "report_date": date.today().isoformat(),
            "project_directory": project_dir,
            "billing_source": billing_file.name,
            "billing_period": "",  # Extracted if available
        },
        "summary": {
            "total_monthly_spend": round(total_spend, 2),
            "service_count": len(services_list),
            "currency": "USD",
        },
        "services": services_list,
        "commitments": {
            "has_active_cuds": has_cuds,
            "total_monthly_commitment_fees": round(total_commitment_fees, 2),
            "total_monthly_cud_credits": round(total_cud_credits, 2),
            "effective_discount_percent": effective_discount,
            "details": commitment_details,
        },
        "cost_basis": {
            "uses_list_price": True,
            "total_at_list": round(total_spend, 2),
            "total_net_of_discounts": round(total_net, 2),
            "discount_breakdown": {k: round(v, 2) for k, v in discount_credits.items()},
        },
        "ai_signals": {
            "detected": ai_detected,
            "confidence": ai_confidence,
            "services": sorted(all_ai_services),
        },
    }

    # Write output
    if output_dir:
        out_path = Path(output_dir) / "billing-profile.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(profile, f, indent=2)
        logger.info("Wrote billing-profile.json to %s", out_path)

    return {"status": "ok", "profile": profile, "ai_signals_detected": ai_detected}
