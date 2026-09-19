#!/usr/bin/env python3
"""Assert a Render Design run against expected-render-basic.json.

Covers the core render-to-aws service-type routing rules:
  - web_service → Elastic Beanstalk (default compute target)
  - background_worker → ECS Fargate (always, regardless of compute_target default)
  - postgres → RDS PostgreSQL
  - key_value → ElastiCache Redis

Also validates the Render plan sizing tables: all Fargate rows in both
web-service-fargate-sizing.json and worker-fargate-sizing.json must
have valid Fargate CPU/memory pairings per the AWS Fargate task spec.

Usage:
    python3 check_expected_render_basic.py <migration_run_dir>

Exits 0 on PASS, 1 on FAIL. Stdlib only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

FAILS: list[str] = []
NOTES: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        FAILS.append(msg)


def load(path: Path) -> dict | list | None:
    if not path.exists():
        FAILS.append(f"missing {path.name} in {path.parent}")
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        FAILS.append(f"{path.name} is not valid JSON: {e}")
        return None


def memory_allowed(spec: dict, memory: int) -> bool:
    if "values" in spec:
        return memory in spec["values"]
    lo, hi, step = spec["min"], spec["max"], spec["step"]
    return lo <= memory <= hi and (memory - lo) % step == 0


def check_sizing_tables(plugin_root: Path, exp: dict) -> None:
    spec = exp.get("sizing_tables", {})
    matrix = exp.get("fargate_cpu_memory_matrix", {})

    required_compute = spec.get("required_plans_in_compute_tables", [])
    required_data = spec.get("required_plans_in_data_tables", [])

    for table_key in ("web_eb", "web_fargate", "worker_fargate"):
        table_path = spec.get(table_key)
        if not table_path:
            continue
        data = load(plugin_root / table_path)
        if data is None:
            continue
        rows = {r["render_plan"]: r for r in data.get("rows", [])}
        for plan in required_compute:
            check(plan in rows, f"{table_key} sizing table has no '{plan}' row")

        # Validate Fargate rows against the CPU/memory matrix
        if "fargate" in table_key:
            for plan, row in rows.items():
                cpu = row.get("fargate_cpu")
                memory = row.get("fargate_memory_mb")
                if cpu is None or memory is None:
                    continue
                spec_for_cpu = matrix.get(str(cpu))
                if spec_for_cpu is None:
                    FAILS.append(
                        f"{table_key} row '{plan}': fargate_cpu={cpu} is not a valid Fargate task CPU value"
                    )
                    continue
                check(
                    memory_allowed(spec_for_cpu, memory),
                    f"{table_key} row '{plan}': cpu={cpu} with memory={memory} MiB is not a valid Fargate pairing",
                )

    for table_key in ("postgres_rds", "redis_elasticache"):
        table_path = spec.get(table_key)
        if not table_path:
            continue
        data = load(plugin_root / table_path)
        if data is None:
            continue
        rows = {r["render_plan"]: r for r in data.get("rows", [])}
        for plan in required_data:
            check(plan in rows, f"{table_key} sizing table has no '{plan}' row")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    run_dir = Path(sys.argv[1])
    fixture_dir = Path(__file__).resolve().parent
    plugin_root = fixture_dir.parent.parent  # fixtures/<set>/ -> plugin root
    exp = load(fixture_dir / "expected-render-basic.json")
    if exp is None:
        _report()
        return 1

    check_sizing_tables(plugin_root, exp)

    inventory = load(run_dir / "render-resource-inventory.json")
    design = load(run_dir / "aws-design.json")
    if inventory is None or design is None:
        _report()
        return 1

    services = design.get("services") or []
    by_source: dict[str, list[dict]] = {}
    for svc in services:
        by_source.setdefault(str(svc.get("source_resource_id")), []).append(svc)

    render_services = inventory.get("services", [])
    check(bool(render_services), "inventory has no services to check")

    for rs in render_services:
        sid = str(rs.get("service_id"))
        stype = rs.get("service_type")
        mapped = by_source.get(sid, [])
        if exp.get("every_service_must_map"):
            check(bool(mapped), f"render service {sid} ({stype}) has no service in the design — silently dropped")
        if not mapped:
            continue

        # background_worker MUST always route to Fargate regardless of compute_target default
        if stype == "background_worker":
            check(
                any(s.get("aws_service") == "Fargate" for s in mapped),
                f"background_worker {sid} was not routed to Fargate "
                f"(got {[s.get('aws_service') for s in mapped]})",
            )

    for want in exp.get("expected_services", []):
        rid = want["source_resource_id"]
        mapped = [s for s in by_source.get(rid, []) if s.get("aws_service") == want["aws_service"]]
        check(bool(mapped), f"no {want['aws_service']} service for {rid}")
        if not mapped:
            continue
        cfg = mapped[0].get("aws_config") or {}
        for key, value in (want.get("aws_config") or {}).items():
            check(cfg.get(key) == value, f"{rid}: aws_config.{key}={cfg.get(key)!r} want {value!r}")

    warnings_list = design.get("warnings") or []
    warnings = " | ".join(str(w) for w in warnings_list)
    for sub in exp.get("required_warning_substrings", []):
        check(sub in warnings, f"missing expected warning substring: {sub!r}")
    for sub in exp.get("forbidden_warning_substrings", []):
        check(sub not in warnings, f"design carries a forbidden warning substring: {sub!r}")

    if FAILS:
        _report()
        return 1
    _print_notes()
    print("PASS — expected-render-basic.json assertions hold")
    return 0


def _print_notes() -> None:
    for n in NOTES:
        print(f"note: {n}")


def _report() -> None:
    _print_notes()
    print(f"FAIL ({len(FAILS)}):")
    for f in FAILS:
        print(f"  - {f}")


if __name__ == "__main__":
    sys.exit(main())
