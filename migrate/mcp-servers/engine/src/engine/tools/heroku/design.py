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

    # Load knowledge tables
    dyno_types = knowledge.get("heroku-to-aws/design/dyno-types", {}).get("types", {})
    postgres_plans = knowledge.get("heroku-to-aws/design/postgres-plans", {}).get("plans", {})
    redis_plans = knowledge.get("heroku-to-aws/design/redis-plans", {}).get("plans", {})
    kafka_plans = knowledge.get("heroku-to-aws/design/kafka-plans", {}).get("plans", {})
    fast_path_data = knowledge.get("heroku-to-aws/design/fast-path-addons", {})
    fast_path = fast_path_data.get("mappings", {})
    fp_aliases = fast_path_data.get("prefix_aliases", {})

    # Extract preferences
    target_region = preferences.get("global", {}).get("target_region", "us-east-1")
    availability = preferences.get("global", {}).get("availability", "multi-az")
    database_ha = preferences.get("data", {}).get("database_ha", availability)
    log_retention = preferences.get("operational", {}).get("log_retention_days", 30)

    services = []
    deferred = []
    warnings = []
    spaces = []

    resources = inventory.get("resources", [])

    for res in resources:
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
            services.append({
                "service_id": f"fargate:{app}:{process_type}",
                "source_resource_id": rid,
                "heroku_app": app,
                "aws_service": "Fargate",
                "confidence": "deterministic",
                "aws_config": {
                    "region": target_region,
                    "task_cpu": sizing["cpu"],
                    "task_memory": sizing["memory"],
                    "desired_count": quantity,
                    "process_type": process_type,
                    "load_balancer": process_type == "web",
                },
            })
            if process_type == "web":
                services.append({
                    "service_id": f"alb:{app}:{process_type}",
                    "source_resource_id": rid,
                    "heroku_app": app,
                    "aws_service": "ALB",
                    "confidence": "deterministic",
                    "aws_config": {
                        "region": target_region,
                        "scheme": "internet-facing",
                        "target_group": f"fargate:{app}:{process_type}",
                    },
                })

        elif rtype == "addon":
            addon_service = config.get("addon_service", "")
            plan = config.get("plan", "").lower()

            if addon_service == "heroku-postgresql":
                pg = postgres_plans.get(plan)
                if not pg:
                    deferred.append({"addon_name": addon_service, "addon_plan": plan, "provider": "heroku", "reason": f"Unrecognized plan: {plan}", "recommendation": "Engage AWS account team"})
                    continue
                use_aurora = database_ha in ("multi-az-ha", "multi-region")
                instance_class = pg["aurora"] if use_aurora else pg["rds"]
                services.append({
                    "service_id": f"rds:{app}:postgres",
                    "source_resource_id": rid,
                    "heroku_app": app,
                    "aws_service": "Aurora PostgreSQL" if use_aurora else "RDS PostgreSQL",
                    "confidence": "deterministic",
                    "aws_config": {
                        "region": target_region,
                        "instance_class": instance_class,
                        "multi_az": database_ha != "single-az",
                        "storage_gb": pg["storage_gb"],
                        "engine_version": "15",
                        "rds_proxy": pg["pooling"],
                    },
                })

            elif addon_service == "heroku-redis":
                rd = redis_plans.get(plan)
                if not rd:
                    deferred.append({"addon_name": addon_service, "addon_plan": plan, "provider": "heroku", "reason": f"Unrecognized plan: {plan}", "recommendation": "Engage AWS account team"})
                    continue
                services.append({
                    "service_id": f"elasticache:{app}:redis",
                    "source_resource_id": rid,
                    "heroku_app": app,
                    "aws_service": "ElastiCache Redis",
                    "confidence": "deterministic",
                    "aws_config": {
                        "region": target_region,
                        "node_type": rd["node_type"],
                        "multi_az": rd["ha"],
                        "automatic_failover": rd["ha"],
                        "transit_encryption": rd["encryption"],
                        "engine_version": rd["version"],
                    },
                })

            elif addon_service == "heroku-kafka":
                kf = kafka_plans.get(plan)
                if not kf:
                    deferred.append({"addon_name": addon_service, "addon_plan": plan, "provider": "heroku", "reason": f"Unrecognized plan: {plan}", "recommendation": "Engage AWS account team"})
                    continue
                services.append({
                    "service_id": f"msk:{app}:kafka",
                    "source_resource_id": rid,
                    "heroku_app": app,
                    "aws_service": "Amazon MSK",
                    "confidence": "deterministic",
                    "aws_config": {
                        "region": target_region,
                        "broker_instance_type": kf["broker_type"],
                        "storage_per_broker_gb": kf["storage_gb"],
                        "broker_count": kf["brokers"],
                        "availability_zones": kf["azs"],
                        "replication_factor": kf["replication"],
                    },
                })

            else:
                # Fast-path lookup
                normalized = _normalize_addon(addon_service, fp_aliases)
                fp_entry = fast_path.get(normalized)
                if fp_entry:
                    aws_svc = " + ".join(fp_entry["aws_services"])
                    services.append({
                        "service_id": f"{fp_entry['aws_services'][0].lower().replace(' ', '_')}:{app}:{addon_service}",
                        "source_resource_id": rid,
                        "heroku_app": app,
                        "aws_service": aws_svc,
                        "confidence": "deterministic",
                        "aws_config": {"region": target_region, "services": fp_entry["aws_services"]},
                    })
                else:
                    deferred.append({"addon_name": addon_service, "addon_plan": plan, "provider": config.get("provider", "unknown"), "reason": "Not found in fast-path table", "recommendation": "Engage AWS account team"})

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

    # Write output
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
