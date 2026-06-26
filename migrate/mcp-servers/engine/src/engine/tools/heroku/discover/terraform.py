"""Scan Heroku Terraform files and extract resource inventory.

Parses .tf files for heroku_* resources, extracts attributes,
resolves cross-references, integrates Procfile/app.json, detects
Cedar/Fir generation, and writes _terraform-discovery.json.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("engine.heroku.discover.terraform")

HEROKU_TYPES = {"heroku_app", "heroku_addon", "heroku_formation", "heroku_domain",
                "heroku_config_association", "heroku_pipeline", "heroku_space",
                "heroku_pipeline_coupling", "heroku_space_peering_connection_accepter"}

SKIP_DIRS = {".terraform", "node_modules", ".git", "__pycache__"}

# Regex for resource blocks
RESOURCE_RE = re.compile(
    r'resource\s+"(heroku_\w+)"\s+"(\w+)"\s*\{', re.MULTILINE
)
# Simple attribute extraction: key = "value" or key = number or key = bool
ATTR_RE = re.compile(r'^\s*(\w+)\s*=\s*(.+)$', re.MULTILINE)
# Reference pattern
REF_RE = re.compile(r'(heroku_\w+\.\w+)\.(id|name)')


def _find_tf_files(project_dir: Path) -> list[Path]:
    """Find all .tf files, excluding skip dirs."""
    files = []
    for path in project_dir.rglob("*.tf"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        files.append(path)
    return sorted(files)


def _extract_block(content: str, start: int) -> str:
    """Extract block body from opening brace position."""
    depth = 0
    i = content.index("{", start)
    block_start = i + 1
    for j in range(i, len(content)):
        if content[j] == "{":
            depth += 1
        elif content[j] == "}":
            depth -= 1
            if depth == 0:
                return content[block_start:j]
    return content[block_start:]


def _parse_value(raw: str) -> Any:
    """Parse a Terraform attribute value."""
    raw = raw.strip().rstrip(",")
    # String
    if raw.startswith('"') and raw.endswith('"'):
        return raw[1:-1]
    # Boolean
    if raw == "true":
        return True
    if raw == "false":
        return False
    # Number
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        pass
    # Reference
    if REF_RE.search(raw):
        return f"ref:{raw}"
    # Variable interpolation
    if "var." in raw:
        return f"var:{raw}"
    return raw


def _extract_attributes(block: str) -> dict:
    """Extract top-level key=value attributes from a block."""
    attrs = {}
    for match in ATTR_RE.finditer(block):
        key = match.group(1)
        val = _parse_value(match.group(2))
        attrs[key] = val
    return attrs


def _parse_procfile(project_dir: Path) -> dict[str, str]:
    """Parse Procfile into {process_type: command}."""
    for path in [project_dir / "Procfile"] + list(project_dir.rglob("Procfile")):
        if path.exists():
            procs = {}
            for line in path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" in line:
                    ptype, cmd = line.split(":", 1)
                    procs[ptype.strip()] = cmd.strip()
            return procs
    return {}


def _parse_app_json(project_dir: Path) -> dict | None:
    """Parse app.json if present."""
    for path in [project_dir / "app.json"] + list(project_dir.rglob("app.json")):
        if path.exists():
            try:
                return json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                return None
    return None


def _detect_generation(stack: str | None) -> str:
    """Detect Cedar/Fir from stack attribute."""
    if not stack:
        return "unknown"
    s = stack.lower()
    if any(x in s for x in ["heroku-20", "heroku-22", "heroku-24"]):
        return "cedar"
    if "fir" in s or "cnb" in s:
        return "fir"
    return "unknown"


def _map_resource(tf_type: str, tf_name: str, attrs: dict, tf_file: str,
                  app_lookup: dict) -> dict:
    """Map a Terraform resource to inventory format."""
    # Resolve app reference
    app_id_raw = attrs.get("app_id", attrs.get("app", ""))
    heroku_app = "unassociated"
    if isinstance(app_id_raw, str):
        if app_id_raw.startswith("ref:"):
            ref_name = app_id_raw[4:].split(".")[1] if "." in app_id_raw[4:] else ""
            heroku_app = app_lookup.get(ref_name, "unassociated")
        else:
            heroku_app = app_id_raw

    if tf_type == "heroku_app":
        app_name = attrs.get("name", tf_name)
        return {
            "resource_id": f"app:{app_name}",
            "resource_type": "app",
            "heroku_app": app_name,
            "config": {
                "app_name": app_name,
                "region": attrs.get("region"),
                "stack": attrs.get("stack"),
                "space": attrs.get("space"),
                "organization": attrs.get("organization"),
                "buildpacks": attrs.get("buildpacks"),
                "acm_enabled": attrs.get("acm"),
            },
            "source": "terraform",
            "tf_file": tf_file,
            "tf_resource_name": tf_name,
        }

    if tf_type == "heroku_addon":
        plan_raw = attrs.get("plan", "unknown:unknown")
        parts = plan_raw.split(":", 1) if isinstance(plan_raw, str) else ["unknown", "unknown"]
        addon_service = parts[0] if parts else "unknown"
        plan_tier = parts[1] if len(parts) > 1 else "unknown"
        return {
            "resource_id": f"addon:{heroku_app}:{addon_service}:{plan_tier}",
            "resource_type": "addon",
            "heroku_app": heroku_app,
            "config": {"addon_service": addon_service, "plan": plan_tier, "provider": "heroku"},
            "source": "terraform",
            "tf_file": tf_file,
            "tf_resource_name": tf_name,
        }

    if tf_type == "heroku_formation":
        process_type = attrs.get("type", "unknown")
        return {
            "resource_id": f"formation:{heroku_app}:{process_type}",
            "resource_type": "formation",
            "heroku_app": heroku_app,
            "config": {
                "process_type": process_type,
                "command": None,  # Filled from Procfile
                "dyno_type": attrs.get("size", "unknown"),
                "quantity": attrs.get("quantity", 0),
            },
            "source": "terraform",
            "tf_file": tf_file,
            "tf_resource_name": tf_name,
        }

    if tf_type == "heroku_domain":
        hostname = attrs.get("hostname", "unknown")
        return {
            "resource_id": f"domain:{heroku_app}:{hostname}",
            "resource_type": "domain",
            "heroku_app": heroku_app,
            "config": {"hostname": hostname, "sni_endpoint": attrs.get("sni_endpoint_id")},
            "source": "terraform",
            "tf_file": tf_file,
            "tf_resource_name": tf_name,
        }

    if tf_type == "heroku_config_association":
        # Extract keys only from vars block (security: no values)
        vars_keys = [k for k in attrs if k not in ("app_id", "app")]
        return {
            "resource_id": f"config:{heroku_app}",
            "resource_type": "config",
            "heroku_app": heroku_app,
            "config": {"config_var_keys": vars_keys},
            "source": "terraform",
            "tf_file": tf_file,
            "tf_resource_name": tf_name,
        }

    if tf_type == "heroku_pipeline":
        pipeline_name = attrs.get("name", tf_name)
        return {
            "resource_id": f"pipeline:{pipeline_name}",
            "resource_type": "pipeline",
            "heroku_app": "unassociated",
            "config": {"pipeline_name": pipeline_name, "stages": [], "review_apps_enabled": False, "detection_status": "detect-only"},
            "source": "terraform",
            "tf_file": tf_file,
            "tf_resource_name": tf_name,
        }

    if tf_type == "heroku_space":
        space_name = attrs.get("name", tf_name)
        return {
            "resource_id": f"space:{space_name}",
            "resource_type": "space",
            "heroku_app": "unassociated",
            "config": {
                "space_name": space_name,
                "region": attrs.get("region"),
                "shield": attrs.get("shield", False),
                "organization": attrs.get("organization"),
                "peering": {"detected": False, "vpc_id": None, "peer_cidr": None},
            },
            "source": "terraform",
            "tf_file": tf_file,
            "tf_resource_name": tf_name,
        }

    # Fallback for coupling/peering (handled separately)
    return None


def scan_heroku_terraform(project_dir: str, migration_dir: str | None = None) -> dict[str, Any]:
    """Scan Terraform files for Heroku resources and write discovery output.

    Args:
        project_dir: Absolute path to the project root.
        migration_dir: If provided, writes _terraform-discovery.json here.

    Returns:
        Dict with resources, apps, metadata, and any parse warnings.
    """
    root = Path(project_dir)
    if not root.is_dir():
        return {"status": "error", "reason": f"Directory not found: {project_dir}"}

    # Find .tf files
    tf_files = _find_tf_files(root)
    if not tf_files:
        logger.info("No .tf files found in %s", project_dir)
        return {"status": "skipped", "reason": "No .tf files found"}

    logger.info("Found %d .tf files in %s", len(tf_files), project_dir)

    # First pass: extract all resource blocks
    raw_resources = []
    parse_warnings = []
    for tf_file in tf_files:
        try:
            content = tf_file.read_text()
        except OSError as e:
            parse_warnings.append(f"Cannot read {tf_file}: {e}")
            continue

        for match in RESOURCE_RE.finditer(content):
            tf_type = match.group(1)
            tf_name = match.group(2)
            if tf_type not in HEROKU_TYPES:
                continue
            try:
                block = _extract_block(content, match.start())
                attrs = _extract_attributes(block)
                rel_file = str(tf_file.relative_to(root))
                raw_resources.append({"type": tf_type, "name": tf_name, "attrs": attrs, "file": rel_file})
            except Exception as e:
                parse_warnings.append(f"Failed to parse {tf_type}.{tf_name} in {tf_file.name}: {e}")

    if not raw_resources:
        logger.info("No heroku_* resources found in .tf files")
        return {"status": "skipped", "reason": "No heroku_* resources found in .tf files"}

    logger.info("Extracted %d raw heroku_* resource blocks", len(raw_resources))

    # Build app lookup (tf_name → app_name)
    app_lookup = {}
    for r in raw_resources:
        if r["type"] == "heroku_app":
            app_lookup[r["name"]] = r["attrs"].get("name", r["name"])

    # Map resources to inventory format
    resources = []
    couplings = []
    peerings = []
    unresolved = []

    for r in raw_resources:
        if r["type"] == "heroku_pipeline_coupling":
            couplings.append(r)
            continue
        if r["type"] == "heroku_space_peering_connection_accepter":
            peerings.append(r)
            continue

        mapped = _map_resource(r["type"], r["name"], r["attrs"], r["file"], app_lookup)
        if mapped:
            if mapped["heroku_app"] == "unassociated" and r["type"] not in ("heroku_pipeline", "heroku_space"):
                unresolved.append({"resource": mapped["resource_id"], "reason": "app_reference_unresolved"})
            resources.append(mapped)

    # Apply pipeline couplings
    for coupling in couplings:
        attrs = coupling["attrs"]
        stage = attrs.get("stage", "unknown")
        app_ref = attrs.get("app_id", "")
        pipeline_ref = attrs.get("pipeline", "")
        # Resolve app
        app_name = "unknown"
        if isinstance(app_ref, str) and app_ref.startswith("ref:"):
            ref_name = app_ref[4:].split(".")[1] if "." in app_ref[4:] else ""
            app_name = app_lookup.get(ref_name, "unknown")
        # Find pipeline and add stage
        for res in resources:
            if res["resource_type"] == "pipeline":
                res["config"]["stages"].append({"stage": stage, "app": app_name})
                break

    # Apply space peering
    for peering in peerings:
        attrs = peering["attrs"]
        space_ref = attrs.get("space", "")
        for res in resources:
            if res["resource_type"] == "space":
                res["config"]["peering"]["detected"] = True
                res["config"]["peering"]["vpc_id"] = attrs.get("vpc_peering_connection_id")
                break

    # Integrate Procfile
    procfile = _parse_procfile(root)
    procfile_found = bool(procfile)
    for proc_type, cmd in procfile.items():
        matched = False
        for res in resources:
            if res["resource_type"] == "formation" and res["config"]["process_type"] == proc_type:
                res["config"]["command"] = cmd
                matched = True
        if not matched:
            # Procfile declares process not in Terraform
            app_name = list(app_lookup.values())[0] if app_lookup else "unknown"
            resources.append({
                "resource_id": f"formation:{app_name}:{proc_type}",
                "resource_type": "formation",
                "heroku_app": app_name,
                "config": {"process_type": proc_type, "command": cmd, "dyno_type": "unknown", "quantity": 0},
                "source": "procfile",
                "tf_file": None,
                "tf_resource_name": None,
            })

    # Integrate app.json
    app_json = _parse_app_json(root)
    app_json_found = app_json is not None

    # Cedar/Fir detection
    apps = []
    for res in resources:
        if res["resource_type"] == "app":
            stack = res["config"].get("stack")
            # Also check app.json stack
            if not stack and app_json and "stack" in app_json:
                stack = app_json["stack"]
                res["config"]["stack"] = stack
            generation = _detect_generation(stack)
            apps.append({
                "app_name": res["config"]["app_name"],
                "heroku_generation": generation,
                "generation_action": "detect_only",
                "space": res["config"].get("space"),
            })

    # Build output
    discovery_sources = ["terraform"]
    if procfile_found:
        discovery_sources.append("procfile")
    if app_json_found:
        discovery_sources.append("app_json")

    output = {
        "resources": resources,
        "apps": apps,
        "terraform_metadata": {
            "found": True,
            "tf_files_scanned": len(tf_files),
            "resource_types_extracted": sorted({r["type"] for r in raw_resources}),
            "parse_warnings": parse_warnings,
        },
        "metadata": {
            "discovery_sources": discovery_sources,
            "confidence": "full" if not parse_warnings else "reduced",
            "total_apps_discovered": len(apps),
        },
        "unresolved_references": unresolved,
    }

    # Write output
    if migration_dir:
        out_path = Path(migration_dir) / "_terraform-discovery.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(output, f, indent=2)
        logger.info("Wrote _terraform-discovery.json: %d resources, %d apps", len(resources), len(apps))

    return {"status": "ok", "summary": {
        "total_resources": len(resources),
        "total_apps": len(apps),
        "discovery_sources": discovery_sources,
        "parse_warnings": len(parse_warnings),
        "unresolved_references": len(unresolved),
    }}
