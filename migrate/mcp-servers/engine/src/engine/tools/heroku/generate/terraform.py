"""Generate Terraform files from aws-design.json using templates.

Reads design, picks templates per service type, substitutes values,
writes .tf files to migration_dir/terraform/.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("engine.heroku.generate.terraform")


def _sanitize(name: str) -> str:
    """Sanitize a name for Terraform resource identifiers."""
    return re.sub(r"[^a-z0-9_]", "_", name.lower().strip())


def _substitute(template: str, values: dict) -> str:
    """Replace {{key}} placeholders with values."""
    result = template
    for key, val in values.items():
        placeholder = "{{" + key + "}}"
        if isinstance(val, bool):
            result = result.replace(placeholder, "true" if val else "false")
        elif isinstance(val, (int, float)):
            result = result.replace(placeholder, str(val))
        elif isinstance(val, list):
            result = result.replace(placeholder, json.dumps(val))
        elif val is None:
            result = result.replace(placeholder, "null")
        else:
            result = result.replace(placeholder, str(val))
    return result


def _extract_repeat_block(template: str, block_name: str) -> str:
    """Extract content between REPEAT_START and REPEAT_END markers."""
    pattern = rf"# --- REPEAT_START {block_name} ---\n(.*?)# --- REPEAT_END {block_name} ---"
    match = re.search(pattern, template, re.DOTALL)
    return match.group(1) if match else ""


def _render_static(template: str) -> str:
    """Remove REPEAT blocks from a template (keep only non-repeated content)."""
    return re.sub(r"# --- REPEAT_START \w+ ---\n.*?# --- REPEAT_END \w+ ---\n?", "", template, flags=re.DOTALL)


def generate_terraform(migration_dir: str, knowledge: dict) -> dict[str, Any]:
    """Generate Terraform files from design using templates.

    Args:
        migration_dir: Path to migration run directory.
        knowledge: Knowledge store dict (contains templates).

    Returns:
        Dict with status and list of files written.
    """
    mdir = Path(migration_dir)
    design = None
    design_path = mdir / "aws-design.json"
    if design_path.exists():
        with open(design_path) as f:
            design = json.load(f)

    if not design:
        return {"status": "error", "reason": "aws-design.json not found"}

    prefs_path = mdir / "preferences.json"
    preferences = {}
    if prefs_path.exists():
        with open(prefs_path) as f:
            preferences = json.load(f)

    # Resolve template directory. Search upward from this file for the knowledge dir
    # (dev layout: <engine>/knowledge/...) and also check the bundled package location
    # (<engine_pkg>/knowledge/...). Robust to how deeply this module is nested.
    rel = Path("knowledge") / "heroku-to-aws" / "templates"
    candidates = [parent / rel for parent in Path(__file__).resolve().parents]
    templates_dir = next((c for c in candidates if c.is_dir()), None)
    if templates_dir is None:
        return {"status": "error", "reason": "Templates directory not found"}

    # Setup output dir
    tf_dir = mdir / "terraform"
    tf_dir.mkdir(parents=True, exist_ok=True)

    services = design.get("services", [])
    vpc_design = design.get("vpc_design", {})
    region = preferences.get("global", {}).get("target_region", "us-east-1")
    project_name = "heroku-migration"
    log_retention = preferences.get("operational", {}).get("log_retention_days", 30)
    vpc_cidr = vpc_design.get("cidr_block", "10.0.0.0/16")

    files_written = []

    # 1. main.tf (static)
    main_tmpl = (templates_dir / "main.tf.tmpl").read_text()
    (tf_dir / "main.tf").write_text(main_tmpl)
    files_written.append("main.tf")

    # 2. variables.tf
    vars_tmpl = (templates_dir / "variables.tf.tmpl").read_text()
    vars_out = _substitute(vars_tmpl, {"region": region, "project_name": project_name, "vpc_cidr": vpc_cidr})
    (tf_dir / "variables.tf").write_text(vars_out)
    files_written.append("variables.tf")

    # 3. VPC
    if vpc_design.get("mode") == "new_vpc":
        vpc_tmpl = (templates_dir / "vpc-new.tf.tmpl").read_text()
        (tf_dir / "vpc.tf").write_text(vpc_tmpl)
    else:
        vpc_tmpl = (templates_dir / "vpc-existing.tf.tmpl").read_text()
        vpc_out = _substitute(vpc_tmpl, {"vpc_id": vpc_design.get("existing_vpc_id", "")})
        (tf_dir / "vpc.tf").write_text(vpc_out)
    files_written.append("vpc.tf")

    # VPC reference for security groups
    vpc_id_ref = "aws_vpc.main.id" if vpc_design.get("mode") == "new_vpc" else f'"{vpc_design.get("existing_vpc_id", "")}"'
    private_subnets_ref = "[aws_subnet.private_a.id, aws_subnet.private_b.id]" if vpc_design.get("mode") == "new_vpc" else json.dumps(vpc_design.get("subnet_ids", []))
    public_subnets_ref = "[aws_subnet.public_a.id, aws_subnet.public_b.id]" if vpc_design.get("mode") == "new_vpc" else private_subnets_ref

    # 4. security.tf
    sec_tmpl = (templates_dir / "security.tf.tmpl").read_text()
    sec_out = _substitute(sec_tmpl, {"vpc_id": vpc_id_ref})
    (tf_dir / "security.tf").write_text(sec_out)
    files_written.append("security.tf")

    # 5. compute.tf (Fargate + ALB)
    fargate_services = [s for s in services if s.get("aws_service") == "Fargate"]
    alb_services = [s for s in services if s.get("aws_service") == "ALB"]

    if fargate_services or alb_services:
        compute_tmpl = (templates_dir / "compute.tf.tmpl").read_text()
        static_part = _render_static(compute_tmpl)
        fargate_block = _extract_repeat_block(compute_tmpl, "fargate")
        alb_block = _extract_repeat_block(compute_tmpl, "alb")

        rendered_fargate = []
        for svc in fargate_services:
            cfg = svc.get("aws_config", {})
            app = svc.get("heroku_app", "app")
            pt = cfg.get("process_type", "web")
            lb_block = ""
            if cfg.get("load_balancer"):
                lb_block = f'  load_balancer {{\n    target_group_arn = aws_lb_target_group.{_sanitize(app)}_{pt}.arn\n    container_name  = "{pt}"\n    container_port  = 8080\n  }}'
            port_mappings = '[{ containerPort = 8080, protocol = "tcp" }]' if pt == "web" else "[]"
            vals = {
                "app_sanitized": _sanitize(app), "process_type": pt,
                "heroku_app": app, "task_cpu": cfg.get("task_cpu", 256),
                "task_memory": cfg.get("task_memory", 512),
                "desired_count": cfg.get("desired_count", 1),
                "container_image": f"{project_name}/{app}-{pt}:latest",
                "log_retention": log_retention, "subnets": private_subnets_ref,
                "load_balancer_block": lb_block, "port_mappings": port_mappings,
            }
            rendered_fargate.append(_substitute(fargate_block, vals))

        rendered_alb = []
        for svc in alb_services:
            cfg = svc.get("aws_config", {})
            app = svc.get("heroku_app", "app")
            tg = cfg.get("target_group", "").split(":")[-1] if cfg.get("target_group") else "web"
            vals = {
                "app_sanitized": _sanitize(app), "heroku_app": app,
                "process_type": tg, "public_subnets": public_subnets_ref,
                "vpc_id": vpc_id_ref,
            }
            rendered_alb.append(_substitute(alb_block, vals))

        compute_out = static_part + "\n".join(rendered_fargate) + "\n" + "\n".join(rendered_alb)
        (tf_dir / "compute.tf").write_text(compute_out)
        files_written.append("compute.tf")

    # 6. database.tf
    rds_services = [s for s in services if s.get("aws_service") == "RDS PostgreSQL"]
    aurora_services = [s for s in services if s.get("aws_service") == "Aurora PostgreSQL"]

    if rds_services or aurora_services:
        db_tmpl = (templates_dir / "database.tf.tmpl").read_text()
        static_part = _render_static(db_tmpl)
        rds_block = _extract_repeat_block(db_tmpl, "rds")
        aurora_block = _extract_repeat_block(db_tmpl, "aurora")
        proxy_block = _extract_repeat_block(db_tmpl, "rds_proxy")

        rendered = []
        for svc in rds_services:
            cfg = svc.get("aws_config", {})
            app = svc.get("heroku_app", "app")
            vals = {"app_sanitized": _sanitize(app), "heroku_app": app, "instance_class": cfg.get("instance_class", "db.t4g.micro"), "storage_gb": cfg.get("storage_gb", 20), "multi_az": cfg.get("multi_az", False), "engine_version": cfg.get("engine_version", "15"), "plan": "standard-0"}
            rendered.append(_substitute(rds_block, vals))
            if cfg.get("rds_proxy"):
                rendered.append(_substitute(proxy_block, {"app_sanitized": _sanitize(app), "heroku_app": app, "private_subnets": private_subnets_ref}))

        for svc in aurora_services:
            cfg = svc.get("aws_config", {})
            app = svc.get("heroku_app", "app")
            vals = {"app_sanitized": _sanitize(app), "heroku_app": app, "heroku_app_sanitized": _sanitize(app), "instance_class": cfg.get("instance_class", "db.r6g.large"), "engine_version": cfg.get("engine_version", "15")}
            rendered.append(_substitute(aurora_block, vals))

        db_out = _substitute(static_part, {"private_subnets": private_subnets_ref}) + "\n".join(rendered)
        (tf_dir / "database.tf").write_text(db_out)
        files_written.append("database.tf")

    # 7. cache.tf
    cache_services = [s for s in services if s.get("aws_service") == "ElastiCache Redis"]
    if cache_services:
        cache_tmpl = (templates_dir / "cache.tf.tmpl").read_text()
        cache_block = _extract_repeat_block(cache_tmpl, "elasticache")
        rendered = []
        for svc in cache_services:
            cfg = svc.get("aws_config", {})
            app = svc.get("heroku_app", "app")
            vals = {"app_sanitized": _sanitize(app), "heroku_app": app, "node_type": cfg.get("node_type", "cache.t4g.micro"), "num_nodes": 2 if cfg.get("multi_az") else 1, "engine_version": cfg.get("engine_version", "7.0"), "multi_az": cfg.get("multi_az", False), "automatic_failover": cfg.get("automatic_failover", False), "transit_encryption": cfg.get("transit_encryption", False), "plan": "premium-0", "private_subnets": private_subnets_ref}
            rendered.append(_substitute(cache_block, vals))
        (tf_dir / "cache.tf").write_text("\n".join(rendered))
        files_written.append("cache.tf")

    # 8. messaging.tf
    msk_services = [s for s in services if s.get("aws_service") == "Amazon MSK"]
    if msk_services:
        msg_tmpl = (templates_dir / "messaging.tf.tmpl").read_text()
        msg_block = _extract_repeat_block(msg_tmpl, "msk")
        rendered = []
        for svc in msk_services:
            cfg = svc.get("aws_config", {})
            app = svc.get("heroku_app", "app")
            vals = {"app_sanitized": _sanitize(app), "heroku_app": app, "broker_instance_type": cfg.get("broker_instance_type", "kafka.t3.small"), "broker_count": cfg.get("broker_count", 2), "storage_per_broker_gb": cfg.get("storage_per_broker_gb", 10), "plan": "basic-0", "private_subnets": private_subnets_ref}
            rendered.append(_substitute(msg_block, vals))
        (tf_dir / "messaging.tf").write_text("\n".join(rendered))
        files_written.append("messaging.tf")

    # 8b. eks.tf (EKS cluster + node group + LB controller), only in EKS-mode designs
    eks_cluster = design.get("eks_cluster")
    if eks_cluster:
        eks_tmpl = (templates_dir / "eks.tf.tmpl").read_text()
        static_part = _render_static(eks_tmpl)
        ng = (eks_cluster.get("node_groups") or [{}])[0]
        node_group_type = eks_cluster.get("node_group_type", "managed")
        instance_types = ng.get("instance_types", [])
        common = {
            "cluster_name": eks_cluster.get("cluster_name", "heroku-migration-cluster"),
            "kubernetes_version": eks_cluster.get("kubernetes_version", "1.31"),
            "vpc_id": vpc_id_ref,
            "vpc_cidr": vpc_cidr,
            "subnet_ids": private_subnets_ref,
            "private_subnets": private_subnets_ref,
            "instance_types": instance_types,
            "node_instance_type": instance_types[0] if instance_types else "m6i.large",
            "desired_size": ng.get("desired_size", 2),
            "max_size": ng.get("max_size", 4),
            "min_size": ng.get("min_size", 2),
        }
        # Select exactly one node-group block (never emit both).
        if node_group_type == "self-managed":
            ng_block = _extract_repeat_block(eks_tmpl, "node_group_selfmanaged")
        else:
            ng_block = _extract_repeat_block(eks_tmpl, "node_group_managed")
        ng_out = _substitute(ng_block, common)

        # Data-store SG rules (pod -> RDS/ElastiCache/MSK). The self-managed path creates
        # aws_security_group.eks_nodes; the managed path lets EKS manage the node SG, so
        # these explicit rules are emitted only for self-managed. (Managed-path access is
        # covered as a MIGRATION_GUIDE step.)
        datastore_out = ""
        if node_group_type == "self-managed":
            ds_block = _extract_repeat_block(eks_tmpl, "datastore_sg")
            stores = []
            if any(s.get("aws_service") in ("RDS PostgreSQL", "Aurora PostgreSQL") for s in services):
                stores.append({"store_key": "database", "store_port": 5432, "store_sg": "database", "store_label": "RDS/Aurora PostgreSQL"})
            if any(s.get("aws_service") == "ElastiCache Redis" for s in services):
                stores.append({"store_key": "cache", "store_port": 6379, "store_sg": "cache", "store_label": "ElastiCache Redis"})
            if any(s.get("aws_service") == "Amazon MSK" for s in services):
                stores.append({"store_key": "messaging", "store_port": 9092, "store_sg": "messaging", "store_label": "Amazon MSK"})
            datastore_out = "\n".join(_substitute(ds_block, st) for st in stores)

        eks_out = _substitute(static_part, common) + ng_out + ("\n" + datastore_out if datastore_out else "")
        (tf_dir / "eks.tf").write_text(eks_out)
        files_written.append("eks.tf")

    # 9. outputs.tf
    outputs_tmpl = (templates_dir / "outputs.tf.tmpl").read_text()
    vpc_output = "aws_vpc.main.id" if vpc_design.get("mode") == "new_vpc" else f'"{vpc_design.get("existing_vpc_id", "")}"'
    outputs_out = _substitute(outputs_tmpl, {"vpc_output": vpc_output})
    (tf_dir / "outputs.tf").write_text(outputs_out)
    files_written.append("outputs.tf")

    # 10. .gitignore
    (tf_dir / ".gitignore").write_text(".terraform/\n*.tfstate\n*.tfstate.backup\n.terraform.lock.hcl\n")
    files_written.append(".gitignore")

    logger.info("Generated %d Terraform files in %s", len(files_written), tf_dir)

    return {"status": "ok", "files_written": files_written, "terraform_dir": str(tf_dir)}
