"""Extract billing summary from Heroku billing exports.

Parses Enterprise CSV, Dashboard invoice CSV/JSON, and API invoice JSON
formats. Produces _billing-discovery.json with per-app cost breakdown.
"""

import csv
import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("orchestrator.extract_heroku_billing")

BILLING_GLOBS = ["*billing*.csv", "*invoice*.csv", "*billing*.json", "*invoice*.json"]
SKIP_DIRS = {".git", "node_modules", ".terraform", ".migration"}


def _find_billing_files(project_dir: Path) -> list[Path]:
    """Find billing files in project directory."""
    files = []
    for pattern in BILLING_GLOBS:
        for path in project_dir.rglob(pattern):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            files.append(path)
    return sorted(set(files))


def _detect_csv_format(header: list[str]) -> str | None:
    """Detect CSV format from header row."""
    h = {c.strip().lower() for c in header}
    if "app" in h and ("dyno_units" in h or "dyno_cost" in h or "addon_total" in h):
        return "enterprise_csv"
    if "description" in h and "amount" in h:
        return "invoice_csv"
    if "resource_name" in h and "category" in h and "cost" in h:
        return "line_item_csv"
    return None


def _detect_json_format(data: Any) -> str | None:
    """Detect JSON format from structure."""
    if not isinstance(data, dict):
        return None
    if "charges" in data and "total" in data:
        return "invoice_json"
    if "line_items" in data and "total_amount" in data:
        return "api_invoice_json"
    if "apps" in data and isinstance(data["apps"], list):
        return "enterprise_json"
    return None


def _parse_description(desc: str) -> tuple[str, str]:
    """Parse invoice description into (resource_name, category)."""
    desc_lower = desc.lower()
    # "Dyno usage for app_name" or "app_name - Dyno"
    m = re.search(r"dyno.*?(?:for|[-–])\s*(.+)", desc, re.IGNORECASE)
    if m:
        return m.group(1).strip(), "dyno"
    m = re.search(r"(.+?)\s*[-–]\s*dyno", desc, re.IGNORECASE)
    if m:
        return m.group(1).strip(), "dyno"
    # "Add-on: addon_name for app_name" or "addon_name (app_name)"
    m = re.search(r"add-?on.*?for\s+(.+)", desc, re.IGNORECASE)
    if m:
        return m.group(1).strip(), "addon"
    m = re.search(r".+?\((.+?)\)", desc)
    if m and "addon" in desc_lower:
        return m.group(1).strip(), "addon"
    # Platform/SSL/Support
    if any(x in desc_lower for x in ["platform", "ssl", "support"]):
        return "platform", "platform"
    return "unknown", "other"


def _parse_enterprise_csv(path: Path) -> dict:
    """Parse Heroku Enterprise CSV billing export."""
    items = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            app = (row.get("app") or "").strip()
            if not app:
                continue
            dyno = float(row.get("dyno_units") or row.get("dyno_cost") or 0)
            addon = float(row.get("addon_total") or row.get("addon_cost") or 0)
            platform = float(row.get("platform_total") or row.get("platform_cost") or 0)
            if dyno > 0:
                items.append({"resource_name": app, "category": "dyno", "cost": round(dyno, 2)})
            if addon > 0:
                items.append({"resource_name": app, "category": "addon", "cost": round(addon, 2)})
            if platform > 0:
                items.append({"resource_name": app, "category": "platform", "cost": round(platform, 2)})

    period = row.get("period") or row.get("billing_period") or "" if items else ""
    return {"items": items, "period": period}


def _parse_invoice_csv(path: Path) -> dict:
    """Parse Heroku Dashboard invoice CSV."""
    items = []
    period = ""
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            desc = (row.get("description") or "").strip()
            amount = float(row.get("amount") or 0)
            if amount <= 0:
                continue
            resource_name, category = _parse_description(desc)
            items.append({"resource_name": resource_name, "category": category, "cost": round(amount, 2)})
            if not period:
                ps = row.get("period_start") or ""
                if ps and len(ps) >= 7:
                    period = ps[:7]  # YYYY-MM
    return {"items": items, "period": period}


def _parse_line_item_csv(path: Path) -> dict:
    """Parse Heroku itemized billing CSV."""
    items = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("resource_name") or "").strip()
            category = (row.get("category") or "other").strip().lower()
            cost = float(row.get("cost") or 0)
            if cost > 0:
                items.append({"resource_name": name, "category": category, "cost": round(cost, 2)})
    return {"items": items, "period": ""}


def _parse_invoice_json(data: dict) -> dict:
    """Parse Heroku Dashboard invoice JSON."""
    items = []
    for charge in data.get("charges", []):
        desc = charge.get("description", "")
        amount = float(charge.get("amount", 0))
        if amount <= 0:
            continue
        resource_name, category = _parse_description(desc)
        items.append({"resource_name": resource_name, "category": category, "cost": round(amount, 2)})
    period = (data.get("period_start") or "")[:7]
    return {"items": items, "period": period}


def _parse_api_invoice_json(data: dict) -> dict:
    """Parse Heroku Platform API invoice JSON."""
    items = []
    for li in data.get("line_items", []):
        app_name = li.get("app_name")
        desc = li.get("description", "")
        amount = float(li.get("amount", 0))
        if amount <= 0:
            continue
        if app_name:
            resource_name = app_name
            category = "dyno" if "dyno" in desc.lower() else ("addon" if "addon" in desc.lower() else "other")
        else:
            resource_name, category = _parse_description(desc)
        items.append({"resource_name": resource_name, "category": category, "cost": round(amount, 2)})
    return {"items": items, "period": ""}


def _parse_enterprise_json(data: dict) -> dict:
    """Parse Heroku Enterprise billing JSON."""
    items = []
    for app in data.get("apps", []):
        name = app.get("name", "unknown")
        dyno = float(app.get("dyno_cost", 0))
        addon = float(app.get("addon_cost", 0))
        platform = float(app.get("platform_cost", 0))
        if dyno > 0:
            items.append({"resource_name": name, "category": "dyno", "cost": round(dyno, 2)})
        if addon > 0:
            items.append({"resource_name": name, "category": "addon", "cost": round(addon, 2)})
        if platform > 0:
            items.append({"resource_name": name, "category": "platform", "cost": round(platform, 2)})
    return {"items": items, "period": ""}


def extract_heroku_billing(project_dir: str, migration_dir: str | None = None) -> dict[str, Any]:
    """Extract billing summary from Heroku billing exports.

    Args:
        project_dir: Absolute path to the project root.
        migration_dir: If provided, writes _billing-discovery.json here.

    Returns:
        Dict with status and billing profile summary.
    """
    root = Path(project_dir)
    billing_files = _find_billing_files(root)
    if not billing_files:
        logger.info("No billing files found in %s", project_dir)
        return {"status": "skipped", "reason": "No billing files found"}

    logger.info("Found %d billing file(s) in %s", len(billing_files), project_dir)

    # Try each file until one parses successfully
    parsed = None
    source_file = None
    source_format = None
    warnings = []

    for bf in billing_files:
        try:
            if bf.suffix == ".csv":
                with open(bf, newline="", encoding="utf-8-sig") as f:
                    reader = csv.reader(f)
                    header = next(reader, [])
                fmt = _detect_csv_format(header)
                if not fmt:
                    warnings.append(f"Unrecognized CSV format: {bf.name}")
                    continue
                if fmt == "enterprise_csv":
                    parsed = _parse_enterprise_csv(bf)
                elif fmt == "invoice_csv":
                    parsed = _parse_invoice_csv(bf)
                elif fmt == "line_item_csv":
                    parsed = _parse_line_item_csv(bf)
            else:
                data = json.loads(bf.read_text())
                fmt = _detect_json_format(data)
                if not fmt:
                    warnings.append(f"Unrecognized JSON format: {bf.name}")
                    continue
                if fmt == "invoice_json":
                    parsed = _parse_invoice_json(data)
                elif fmt == "api_invoice_json":
                    parsed = _parse_api_invoice_json(data)
                elif fmt == "enterprise_json":
                    parsed = _parse_enterprise_json(data)

            if parsed and parsed["items"]:
                source_file = bf.name
                source_format = fmt
                break
        except Exception as e:
            warnings.append(f"Failed to parse {bf.name}: {e}")
            continue

    if not parsed or not parsed["items"]:
        logger.warning("No parseable billing data found. Warnings: %s", warnings)
        return {"status": "skipped", "reason": "No parseable billing data found", "warnings": warnings}

    total = round(sum(i["cost"] for i in parsed["items"]), 2)
    logger.info("Parsed billing: $%.2f/month, %d line items, format=%s, file=%s",
                total, len(parsed["items"]), source_format, source_file)

    profile = {
        "billing_profile": {
            "available": True,
            "total_monthly_cost": total,
            "currency": "USD",
            "billing_period": parsed["period"],
            "source_file": source_file,
            "source_format": source_format,
            "line_items": parsed["items"],
            "parse_warnings": warnings,
        }
    }

    if migration_dir:
        out_path = Path(migration_dir) / "_billing-discovery.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(profile, f, indent=2)

    return {"status": "ok", "total_monthly_cost": total, "line_item_count": len(parsed["items"]), "source_format": source_format}
