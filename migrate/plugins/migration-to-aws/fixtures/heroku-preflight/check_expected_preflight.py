#!/usr/bin/env python3
"""Assert a Heroku preflight readiness-check run against expected-preflight.json.

Usage:
    python3 check_expected_preflight.py <migration_run_dir>

Where <migration_run_dir> is expected to contain preflight-report.json produced
by the preflight sidebar. Verifies the structural contract of the report:
  - required top-level fields are present
  - status is one of {pass, warn, blocked}
  - status is consistent with the presence/absence of blockers and quota_items
  - each blockers[] entry has the required fields
  - each quota_items[] entry has the required fields
  - no secret-like material in the report

This is a SMOKE asserter — no golden run dir is committed; the script is
executed against an empty scratch dir by run-asserters.py and MUST exit
non-zero (proving the failure path works). Exits 0 on PASS, 1 on FAIL.
Stdlib only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

FAILS: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        FAILS.append(msg)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    run_dir = Path(sys.argv[1])
    fixture_dir = Path(__file__).resolve().parent
    exp = json.loads((fixture_dir / "expected-preflight.json").read_text())

    report_path = run_dir / "preflight-report.json"
    if not report_path.exists():
        print("FAIL (1):\n  - missing preflight-report.json in run dir")
        return 1

    try:
        report = json.loads(report_path.read_text())
    except json.JSONDecodeError as e:
        print(f"FAIL (1):\n  - preflight-report.json is not valid JSON: {e}")
        return 1

    # --- Required top-level fields ---
    for field in exp["required_top_level_fields"]:
        check(field in report, f"missing required field: {field}")

    # --- Status is a valid value ---
    status = report.get("status")
    check(
        status in exp["status_valid_values"],
        f"status={status!r} is not one of {exp['status_valid_values']}",
    )

    # --- services_checked is a non-negative integer ---
    svc_count = report.get("services_checked")
    check(
        isinstance(svc_count, int) and svc_count >= 0,
        f"services_checked={svc_count!r} is not a non-negative integer",
    )

    # --- blockers and quota_items are arrays ---
    blockers = report.get("blockers", None)
    quota_items = report.get("quota_items", None)
    check(isinstance(blockers, list), "blockers must be an array")
    check(isinstance(quota_items, list), "quota_items must be an array")

    # --- Status consistency ---
    if isinstance(blockers, list) and isinstance(quota_items, list) and status in exp["status_valid_values"]:
        if blockers:
            check(status == "blocked", f"status={status!r} but blockers is non-empty — expected 'blocked'")
        elif quota_items:
            check(status == "warn", f"status={status!r} but quota_items non-empty and blockers empty — expected 'warn'")
        else:
            check(status == "pass", f"status={status!r} but both blockers and quota_items are empty — expected 'pass'")

    # --- blockers entries have required fields ---
    if isinstance(blockers, list):
        for i, item in enumerate(blockers):
            for field in exp["blockers_item_required_fields"]:
                check(
                    isinstance(item, dict) and field in item,
                    f"blockers[{i}] missing required field '{field}'",
                )

    # --- quota_items entries have required fields ---
    if isinstance(quota_items, list):
        for i, item in enumerate(quota_items):
            for field in exp["quota_items_item_required_fields"]:
                check(
                    isinstance(item, dict) and field in item,
                    f"quota_items[{i}] missing required field '{field}'",
                )

    # --- Secret hygiene ---
    doc = report_path.read_text()
    for bad in ("HEROKU_API_KEY", "Bearer ", "sk_live", "postgres://", "AKIA"):
        check(bad not in doc, f"possible secret material in preflight-report.json: {bad}")

    if FAILS:
        print(f"FAIL ({len(FAILS)}):")
        for f in FAILS:
            print(f"  - {f}")
        return 1
    print("PASS — expected-preflight.json assertions hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
