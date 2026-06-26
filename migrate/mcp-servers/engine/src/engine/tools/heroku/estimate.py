"""Estimate AWS costs for a Heroku → AWS migration.

Reads aws-design.json + preferences.json + inventory billing data,
calculates per-service costs, generates comparison and ROI, classifies
complexity, and writes estimation-infra.json.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("engine.heroku.estimate")

HOURS_PER_MONTH = 730


def _read_json(path: Path) -> dict | None:
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def _calc_fargate(config: dict, pricing: dict) -> float:
    cpu = config.get("task_cpu", 256)
    mem = config.get("task_memory", 512)
    count = config.get("desired_count", 1)
    cpu_cost = (cpu / 1024) * pricing["fargate"]["cpu_per_hour"] * HOURS_PER_MONTH
    mem_cost = (mem / 1024) * pricing["fargate"]["memory_gb_per_hour"] * HOURS_PER_MONTH
    return (cpu_cost + mem_cost) * count


def _calc_alb(pricing: dict) -> float:
    return pricing["alb"]["fixed_monthly"] + pricing["alb"]["lcu_per_hour"] * HOURS_PER_MONTH * 0.5  # conservative 0.5 LCU avg


def _calc_rds(config: dict, pricing: dict) -> float:
    instance = config.get("instance_class", "db.t4g.micro")
    rate = pricing["rds_instances"].get(instance, 0.016)
    storage = config.get("storage_gb", 20)
    multi_az = 2 if config.get("multi_az") else 1
    cost = rate * HOURS_PER_MONTH * multi_az + storage * pricing["rds_storage_per_gb"]
    if config.get("rds_proxy"):
        # Estimate 2 vCPUs for proxy
        cost += 2 * pricing["rds_proxy_per_vcpu_hour"] * HOURS_PER_MONTH
    return cost


def _calc_aurora(config: dict, pricing: dict) -> float:
    instance = config.get("instance_class", "db.t4g.medium")
    rate = pricing["rds_instances"].get(instance, 0.065)
    storage = config.get("storage_gb", 20)
    cost = rate * HOURS_PER_MONTH + storage * pricing["aurora_storage_per_gb"]
    if config.get("rds_proxy"):
        cost += 2 * pricing["rds_proxy_per_vcpu_hour"] * HOURS_PER_MONTH
    return cost


def _calc_elasticache(config: dict, pricing: dict) -> float:
    node = config.get("node_type", "cache.t4g.micro")
    rate = pricing["elasticache_nodes"].get(node, 0.016)
    multi = 2 if config.get("multi_az") else 1
    return rate * HOURS_PER_MONTH * multi


def _calc_msk(config: dict, pricing: dict) -> float:
    broker = config.get("broker_instance_type", "kafka.t3.small")
    rate = pricing["msk_brokers"].get(broker, 0.0456)
    count = config.get("broker_count", 2)
    storage = config.get("storage_per_broker_gb", 10) * count
    return rate * HOURS_PER_MONTH * count + storage * pricing["msk_storage_per_gb"]


def _calc_service_cost(service: dict, pricing: dict) -> tuple[float, str]:
    """Calculate monthly cost for a single service. Returns (cost, pricing_source)."""
    aws_svc = service.get("aws_service", "")
    config = service.get("aws_config", {})

    if aws_svc == "Fargate":
        return _calc_fargate(config, pricing), "cached"
    if aws_svc == "EKS":
        # EKS Deployment entries carry no standalone cost — compute is billed via the
        # cluster control plane + EC2 nodes (added once, post-loop). Sentinel "eks_pod"
        # tells the caller to omit this entry from the breakdown entirely.
        return 0.0, "eks_pod"
    if aws_svc == "ALB":
        return _calc_alb(pricing), "cached"
    if aws_svc == "RDS PostgreSQL":
        return _calc_rds(config, pricing), "cached"
    if aws_svc == "Aurora PostgreSQL":
        return _calc_aurora(config, pricing), "cached"
    if aws_svc == "ElastiCache Redis":
        return _calc_elasticache(config, pricing), "cached"
    if aws_svc == "Amazon MSK":
        return _calc_msk(config, pricing), "cached"
    if "CloudWatch" in aws_svc:
        return 5.0, "cached"  # Minimal baseline, observability calculated separately
    if "S3" in aws_svc:
        return 5.0, "cached"  # Minimal storage baseline
    if "SES" in aws_svc:
        return 1.0, "cached"
    if "EventBridge" in aws_svc:
        return 1.0, "cached"
    if "MQ" in aws_svc:
        return 30.0, "cached"  # mq.t3.micro baseline
    if "OpenSearch" in aws_svc:
        return 50.0, "cached"  # t3.small.search baseline
    if "SNS" in aws_svc:
        return 1.0, "cached"

    return 0.0, "unpriced"


def _calc_eks_cluster(eks_cluster: dict, pricing: dict) -> tuple[float, float]:
    """Return (control_plane_monthly, nodes_monthly) for an eks_cluster design entry."""
    control_plane = pricing.get("eks_control_plane_monthly", 73.00)
    node_rates = pricing.get("ec2_nodes", {})
    nodes_monthly = 0.0
    for ng in eks_cluster.get("node_groups", []):
        instance_types = ng.get("instance_types", [])
        rate = node_rates.get(instance_types[0], 0.0) if instance_types else 0.0
        nodes_monthly += rate * HOURS_PER_MONTH * ng.get("desired_size", 0)
    return control_plane, nodes_monthly


def _calc_observability(services: list[dict], log_retention_days: int, pricing: dict) -> dict:
    """Calculate CloudWatch observability costs."""
    log_gb = 0.0
    for svc in services:
        aws = svc.get("aws_service", "")
        count = svc.get("aws_config", {}).get("desired_count", 1)
        if aws == "Fargate":
            log_gb += 3 * count
        elif "RDS" in aws or "Aurora" in aws:
            log_gb += 1
        elif aws == "ALB":
            log_gb += 2
        elif aws == "ElastiCache Redis":
            log_gb += 0.5
        elif aws == "Amazon MSK":
            log_gb += 2 * svc.get("aws_config", {}).get("broker_count", 2)

    retention_months = max(1, log_retention_days / 30)
    metrics_count = max(10, len(services) * 5)
    alarm_count = max(5, len(services) * 2)

    ingestion = log_gb * pricing["cloudwatch"]["log_ingestion_per_gb"]
    storage = log_gb * pricing["cloudwatch"]["log_storage_per_gb"] * retention_months
    metrics = metrics_count * pricing["cloudwatch"]["metric_per_month"]
    alarms = alarm_count * pricing["cloudwatch"]["alarm_per_month"]
    total = ingestion + storage + metrics + alarms

    return {"total": round(total, 2), "log_gb": log_gb, "ingestion": round(ingestion, 2), "storage": round(storage, 2), "metrics": round(metrics, 2), "alarms": round(alarms, 2)}


def _classify_complexity(services: list, monthly_spend: float, preferences: dict) -> dict:
    """Classify migration complexity tier."""
    svc_count = len(services)
    availability = preferences.get("global", {}).get("availability", "")
    compliance = preferences.get("global", {}).get("compliance", "none")
    has_db = any(s.get("aws_service", "") in ("RDS PostgreSQL", "Aurora PostgreSQL", "ElastiCache Redis", "Amazon MQ", "Amazon OpenSearch") for s in services)
    regions = {s.get("aws_config", {}).get("region") for s in services}
    multi_region = len(regions) > 1

    if svc_count >= 9 or monthly_spend > 10000 or multi_region or (compliance and compliance != "none"):
        tier = "large"
    elif svc_count >= 4 or monthly_spend >= 1000 or has_db or availability in ("multi-az", "multi-az-ha"):
        tier = "medium"
    else:
        tier = "small"

    timeline = {"small": "2-6 weeks", "medium": "6-12 weeks", "large": "12-18 weeks"}
    return {"tier": tier, "timeline": timeline[tier], "service_count": svc_count, "has_databases": has_db, "multi_region": multi_region}


def _build_optimizations(services: list, balanced_total: float) -> list:
    """Generate applicable cost optimization opportunities."""
    opps = []
    has_fargate = any(s.get("aws_service") == "Fargate" for s in services)
    has_db = any(s.get("aws_service", "") in ("RDS PostgreSQL", "Aurora PostgreSQL") for s in services)
    has_workers = any(s.get("aws_service") == "Fargate" and s.get("aws_config", {}).get("process_type") != "web" for s in services)

    if has_fargate:
        opps.append({"opportunity": "Compute Savings Plans", "target": "Fargate", "savings_percent": "20-66%", "timing": "post-migration (30-90 days)"})
    if has_db:
        opps.append({"opportunity": "Database Savings Plans", "target": "RDS/Aurora", "savings_percent": "up to 35%", "timing": "post-migration"})
    if has_workers:
        opps.append({"opportunity": "Fargate Spot for Workers", "target": "Fargate (non-web)", "savings_percent": "60-70%", "timing": "during migration"})

    return opps


def estimate_heroku_migration(migration_dir: str, knowledge: dict) -> dict[str, Any]:
    """Estimate AWS costs for a Heroku migration.

    Args:
        migration_dir: Path to migration run directory.
        knowledge: Knowledge store dict.

    Returns:
        Dict with status, summary, and any unpriced services for LLM follow-up.
    """
    mdir = Path(migration_dir)
    design = _read_json(mdir / "aws-design.json")
    preferences = _read_json(mdir / "preferences.json")
    inventory = _read_json(mdir / "heroku-resource-inventory.json")

    if not design:
        return {"status": "error", "reason": "aws-design.json not found"}
    if not preferences:
        return {"status": "error", "reason": "preferences.json not found"}

    pricing = knowledge.get("heroku-to-aws/design/aws-pricing", {})
    services = design.get("services", [])

    if not services:
        return {"status": "error", "reason": "No services in aws-design.json"}

    # Calculate per-service costs
    breakdown = []
    unpriced = []
    balanced_total = 0.0

    for svc in services:
        cost, source = _calc_service_cost(svc, pricing)
        if source == "eks_pod":
            # Omit EKS Deployment lines from the breakdown — cost attributed to the cluster.
            continue
        entry = {"service_id": svc["service_id"], "aws_service": svc["aws_service"], "monthly_cost": round(cost, 2), "pricing_source": source}
        breakdown.append(entry)
        if source == "unpriced":
            unpriced.append(svc["service_id"])
        else:
            balanced_total += cost

    # Observability
    log_retention = preferences.get("operational", {}).get("log_retention_days", 30)
    obs = _calc_observability(services, log_retention, pricing)
    breakdown.append({"service_id": "observability", "aws_service": "CloudWatch", "monthly_cost": obs["total"], "pricing_source": "cached"})
    balanced_total += obs["total"]

    # NAT Gateway (if new VPC)
    if design.get("vpc_design", {}).get("mode") == "new_vpc":
        nat_cost = pricing.get("nat_gateway", {}).get("fixed_monthly", 32.85)
        breakdown.append({"service_id": "nat_gateway", "aws_service": "NAT Gateway", "monthly_cost": nat_cost, "pricing_source": "cached"})
        balanced_total += nat_cost

    # EKS cluster (control plane + EC2 nodes), added once when design is EKS-mode.
    notes = []
    eks_cluster = design.get("eks_cluster")
    if eks_cluster:
        control_plane, nodes_monthly = _calc_eks_cluster(eks_cluster, pricing)
        breakdown.append({"service_id": "eks_control_plane", "aws_service": "EKS Control Plane", "monthly_cost": round(control_plane, 2), "pricing_source": "cached"})
        breakdown.append({"service_id": "eks_nodes", "aws_service": "EKS EC2 Nodes", "monthly_cost": round(nodes_monthly, 2), "pricing_source": "cached"})
        balanced_total += control_plane + nodes_monthly
        notes.append(
            "EKS with EC2 nodes is typically cheaper than Fargate for sustained workloads "
            "(>60% utilization) because there is no per-pod Fargate surcharge. However, EKS has "
            "a higher base cost ($73/month control plane + minimum 2 nodes) and requires "
            "Kubernetes operational expertise."
        )

    balanced_total = round(balanced_total, 2)
    premium_total = round(balanced_total * 1.3, 2)
    optimized_total = round(balanced_total * 0.7, 2)

    # Heroku baseline
    billing = (inventory or {}).get("billing_profile", {})
    heroku_monthly = billing.get("total_monthly_cost") if billing.get("available") else None

    # Comparison
    comparison = None
    if heroku_monthly:
        comparison = {
            "heroku_monthly_baseline": heroku_monthly,
            "balanced": {"aws_monthly": balanced_total, "difference": round(balanced_total - heroku_monthly, 2), "percent_change": round((balanced_total - heroku_monthly) / heroku_monthly * 100, 1)},
            "optimized": {"aws_monthly": optimized_total, "difference": round(optimized_total - heroku_monthly, 2), "percent_change": round((optimized_total - heroku_monthly) / heroku_monthly * 100, 1)},
        }

    # Complexity
    complexity = _classify_complexity(services, balanced_total, preferences)

    # Optimizations
    optimizations = _build_optimizations(services, balanced_total)

    # Recommendation
    if heroku_monthly and balanced_total < heroku_monthly:
        rec_path = "migrate_optimized"
    elif complexity["tier"] == "large":
        rec_path = "migrate_phased"
    else:
        rec_path = "migrate_optimized"

    # Assemble output
    output = {
        "phase": "estimate",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pricing_source": {"status": "cached", "message": "All prices from cached rates"},
        "current_costs": {"source": "billing_data" if heroku_monthly else "unavailable", "heroku_monthly": heroku_monthly},
        "projected_costs": {
            "aws_monthly_premium": premium_total,
            "aws_monthly_balanced": balanced_total,
            "aws_monthly_optimized": optimized_total,
            "breakdown": breakdown,
        },
        "cost_comparison": comparison,
        "notes": notes,
        "optimization_opportunities": optimizations,
        "complexity_tier": complexity["tier"],
        "complexity_timeline": complexity["timeline"],
        "recommendation": {"path": rec_path},
    }

    out_path = mdir / "estimation-infra.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    logger.info("Wrote estimation-infra.json: balanced=$%.2f/mo, tier=%s", balanced_total, complexity["tier"])

    return {
        "status": "ok",
        "summary": {
            "aws_monthly_balanced": balanced_total,
            "aws_monthly_optimized": optimized_total,
            "heroku_monthly": heroku_monthly,
            "complexity_tier": complexity["tier"],
            "timeline": complexity["timeline"],
            "unpriced_services": unpriced,
        },
    }
