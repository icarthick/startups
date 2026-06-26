"""Design Heroku → AWS architecture.

Reads heroku-resource-inventory.json + preferences.json, applies lookup
tables (dyno→Fargate, postgres→RDS/Aurora, redis→ElastiCache, kafka→MSK,
fast-path addons), generates VPC design, and writes aws-design.json.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("engine.heroku.design")


def _read_json(path: Path) -> dict | None:
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def _normalize_addon(name: str, aliases: dict) -> str:
    """Normalize addon name for fast-path matching."""
    n = name.lower().strip()
    if n.startswith("heroku-"):
        n = n[7:]
    n = n.replace("-", " ")
    return aliases.get(n, n)


# --- Helpers ---

def _make_service(service_id: str, aws_service: str, app: str, rid: str, target_region: str, aws_config: dict) -> dict:
    """Build a standard service entry."""
    return {
        "service_id": service_id,
        "source_resource_id": rid,
        "heroku_app": app,
        "aws_service": aws_service,
        "confidence": "deterministic",
        "aws_config": {"region": target_region, **aws_config},
    }


def _make_deferred(addon_name: str, plan: str, provider: str, reason: str) -> dict:
    """Build a standard deferred entry."""
    return {"addon_name": addon_name, "addon_plan": plan, "provider": provider, "reason": reason, "recommendation": "Engage AWS account team"}


# --- Addon Mappers ---

def _map_postgres(config: dict, app: str, rid: str, target_region: str, preferences: dict, knowledge: dict) -> tuple[dict | None, dict | None]:
    plan = config.get("plan", "").lower()
    plans = knowledge.get("heroku-to-aws/design/postgres-plans", {}).get("plans", {})
    pg = plans.get(plan)
    if not pg:
        return None, _make_deferred("heroku-postgresql", plan, "heroku", f"Unrecognized plan: {plan}")

    database_ha = preferences.get("data", {}).get("database_ha", preferences.get("global", {}).get("availability", "multi-az"))
    use_aurora = database_ha in ("multi-az-ha", "multi-region")
    return _make_service(
        f"rds:{app}:postgres",
        "Aurora PostgreSQL" if use_aurora else "RDS PostgreSQL",
        app, rid, target_region,
        {"instance_class": pg["aurora"] if use_aurora else pg["rds"], "multi_az": database_ha != "single-az", "storage_gb": pg["storage_gb"], "engine_version": "15", "rds_proxy": pg["pooling"]},
    ), None


def _map_redis(config: dict, app: str, rid: str, target_region: str, preferences: dict, knowledge: dict) -> tuple[dict | None, dict | None]:
    plan = config.get("plan", "").lower()
    plans = knowledge.get("heroku-to-aws/design/redis-plans", {}).get("plans", {})
    rd = plans.get(plan)
    if not rd:
        return None, _make_deferred("heroku-redis", plan, "heroku", f"Unrecognized plan: {plan}")

    return _make_service(
        f"elasticache:{app}:redis", "ElastiCache Redis", app, rid, target_region,
        {"node_type": rd["node_type"], "multi_az": rd["ha"], "automatic_failover": rd["ha"], "transit_encryption": rd["encryption"], "engine_version": rd["version"]},
    ), None


def _map_kafka(config: dict, app: str, rid: str, target_region: str, preferences: dict, knowledge: dict) -> tuple[dict | None, dict | None]:
    plan = config.get("plan", "").lower()
    plans = knowledge.get("heroku-to-aws/design/kafka-plans", {}).get("plans", {})
    kf = plans.get(plan)
    if not kf:
        return None, _make_deferred("heroku-kafka", plan, "heroku", f"Unrecognized plan: {plan}")

    return _make_service(
        f"msk:{app}:kafka", "Amazon MSK", app, rid, target_region,
        {"broker_instance_type": kf["broker_type"], "storage_per_broker_gb": kf["storage_gb"], "broker_count": kf["brokers"], "availability_zones": kf["azs"], "replication_factor": kf["replication"]},
    ), None


def _map_fast_path(addon_service: str, config: dict, app: str, rid: str, target_region: str, knowledge: dict) -> tuple[dict | None, dict | None]:
    fast_path_data = knowledge.get("heroku-to-aws/design/fast-path-addons", {})
    fast_path = fast_path_data.get("mappings", {})
    fp_aliases = fast_path_data.get("prefix_aliases", {})

    normalized = _normalize_addon(addon_service, fp_aliases)
    fp_entry = fast_path.get(normalized)
    if fp_entry:
        return _make_service(
            f"{fp_entry['aws_services'][0].lower().replace(' ', '_')}:{app}:{addon_service}",
            " + ".join(fp_entry["aws_services"]), app, rid, target_region,
            {"services": fp_entry["aws_services"]},
        ), None

    plan = config.get("plan", "").lower()
    return None, _make_deferred(addon_service, plan, config.get("provider", "unknown"), "Not found in fast-path table")


ADDON_MAPPERS = {
    "heroku-postgresql": _map_postgres,
    "heroku-redis": _map_redis,
    "heroku-kafka": _map_kafka,
}


# --- Main ---

def design_heroku_migration(migration_dir: str, knowledge: dict) -> dict[str, Any]:
    """Design AWS architecture from Heroku inventory + preferences.

    Args:
        migration_dir: Path to migration run directory.
        knowledge: Knowledge store dict.

    Returns:
        Dict with status and design summary.
    """
    mdir = Path(migration_dir)
    inventory = _read_json(mdir / "heroku-resource-inventory.json")
    preferences = _read_json(mdir / "preferences.json")

    if not inventory:
        return {"status": "error", "reason": "heroku-resource-inventory.json not found"}
    if not preferences:
        return {"status": "error", "reason": "preferences.json not found"}

    # Load knowledge
    dyno_types = knowledge.get("heroku-to-aws/design/dyno-types", {}).get("types", {})
    target_region = preferences.get("global", {}).get("target_region", "us-east-1")

    services = []
    deferred = []
    warnings = []
    spaces = []

    for res in inventory.get("resources", []):
        rtype = res.get("resource_type")
        config = res.get("config", {})
        app = res.get("heroku_app", "unknown")
        rid = res.get("resource_id", "")

        if rtype == "formation":
            dyno = config.get("dyno_type", "").lower()
            sizing = dyno_types.get(dyno)
            if not sizing:
                warnings.append(f"Unsupported dyno type: '{dyno}'. Cannot map to Fargate.")
                continue
            process_type = config.get("process_type", "web")
            quantity = max(0, min(config.get("quantity", 1), 100))
            services.append(_make_service(
                f"fargate:{app}:{process_type}", "Fargate", app, rid, target_region,
                {"task_cpu": sizing["cpu"], "task_memory": sizing["memory"], "desired_count": quantity, "process_type": process_type, "load_balancer": process_type == "web"},
            ))
            if process_type == "web":
                services.append(_make_service(
                    f"alb:{app}:{process_type}", "ALB", app, rid, target_region,
                    {"scheme": "internet-facing", "target_group": f"fargate:{app}:{process_type}"},
                ))

        elif rtype == "addon":
            addon_service = config.get("addon_service", "")
            mapper = ADDON_MAPPERS.get(addon_service)
            if mapper:
                entry, defer = mapper(config, app, rid, target_region, preferences, knowledge)
            else:
                entry, defer = _map_fast_path(addon_service, config, app, rid, target_region, knowledge)

            if entry:
                services.append(entry)
            if defer:
                deferred.append(defer)

        elif rtype == "pipeline":
            warnings.append(f"Pipeline '{config.get('pipeline_name', 'unknown')}' detected — CI/CD mapping requires manual configuration")

        elif rtype == "space":
            spaces.append(config)

    # VPC design
    has_peering = any(s.get("peering", {}).get("detected") for s in spaces)
    if has_peering:
        peering_space = next(s for s in spaces if s.get("peering", {}).get("detected"))
        vpc_design = {
            "mode": "existing_vpc",
            "existing_vpc_id": peering_space["peering"].get("vpc_id"),
            "subnet_ids": preferences.get("network", {}).get("subnet_ids", []),
        }
    else:
        vpc_design = {
            "mode": "new_vpc",
            "cidr_block": "10.0.0.0/16",
            "subnets": [
                {"cidr": "10.0.1.0/24", "az": "a", "type": "public"},
                {"cidr": "10.0.2.0/24", "az": "b", "type": "public"},
                {"cidr": "10.0.3.0/24", "az": "a", "type": "private"},
                {"cidr": "10.0.4.0/24", "az": "b", "type": "private"},
            ],
            "internet_gateway": True,
        }

    # Fir detection
    apps = inventory.get("apps", [])
    fir_apps = [a["app_name"] for a in apps if a.get("heroku_generation") == "fir"]
    fir_note = "Fir-generation workloads detected. Deferred to future version." if fir_apps else "No Fir workloads detected; all Cedar generation."
    if fir_apps:
        warnings.append(f"Fir-generation workloads deferred: {', '.join(fir_apps)}")

    # Assemble output
    unique_apps = {s["heroku_app"] for s in services if s["heroku_app"] != "unknown"}
    design = {
        "phase": "design",
        "design_source": inventory.get("metadata", {}).get("discovery_sources", ["terraform"])[0],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metadata": {
            "total_services": len(services),
            "total_apps_migrated": len(unique_apps),
            "fir_workloads_detected": fir_apps,
            "fir_generation_note": fir_note,
        },
        "services": services,
        "deferred": deferred,
        "warnings": warnings,
        "vpc_design": vpc_design,
    }

    out_path = mdir / "aws-design.json"
    with open(out_path, "w") as f:
        json.dump(design, f, indent=2)

    logger.info("Wrote aws-design.json: %d services, %d deferred, %d warnings", len(services), len(deferred), len(warnings))

    return {
        "status": "ok",
        "summary": {
            "total_services": len(services),
            "total_apps_migrated": len(unique_apps),
            "deferred_count": len(deferred),
            "warnings_count": len(warnings),
            "vpc_mode": vpc_design["mode"],
        },
    }
