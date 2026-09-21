#!/usr/bin/env python3
"""Assert an Azure Discover run against expected-discover.json.

Covers the azure-to-aws Discover phase: given a workspace with azurerm Terraform files,
the Discover phase must produce a flat azure-resource-inventory.json with the expected
resource types and IDs, no forbidden clustering fields, and no secret values.

Also verifies the flat resource model invariant: no clustering or dependency fields anywhere
in the inventory.

Usage:
    python3 check_expected_discover.py <migration_run_dir>

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


def load(path: Path) -> dict | None:
    if not path.exists():
        FAILS.append(f"missing {path.name} in {path.parent}")
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        FAILS.append(f"{path.name} is not valid JSON: {e}")
        return None


def check_no_forbidden_fields(obj: object, path: str, forbidden: list[str]) -> None:
    """Recursively check that no forbidden keys exist anywhere in obj."""
    if isinstance(obj, dict):
        for key in obj:
            if key in forbidden:
                FAILS.append(f"forbidden clustering field '{key}' found at {path}.{key}")
            check_no_forbidden_fields(obj[key], f"{path}.{key}", forbidden)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            check_no_forbidden_fields(item, f"{path}[{i}]", forbidden)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    run_dir = Path(sys.argv[1])
    fixture_dir = Path(__file__).resolve().parent
    exp = json.loads((fixture_dir / "expected-discover.json").read_text())

    inventory = load(run_dir / "azure-resource-inventory.json")
    phase_status = load(run_dir / ".phase-status.json")

    if inventory is None:
        _report()
        return 1

    # 1. Metadata fields present
    metadata = inventory.get("metadata") or {}
    for field in exp.get("required_metadata_fields", []):
        check(field in metadata, f"metadata.{field} is missing")

    # 2. discovery_sources
    sources = metadata.get("discovery_sources", [])
    for required in exp.get("discovery_sources_must_include", []):
        check(required in sources, f"discovery_sources must include '{required}', got {sources}")

    # 3. Total count
    resources = inventory.get("resources", [])
    expected_count = exp.get("total_resources_discovered")
    if expected_count is not None:
        check(
            len(resources) == expected_count,
            f"total_resources_discovered={metadata.get('total_resources_discovered')} "
            f"but resources[] has {len(resources)} entries (expected {expected_count})",
        )
        check(
            metadata.get("total_resources_discovered") == len(resources),
            f"metadata.total_resources_discovered ({metadata.get('total_resources_discovered')}) "
            f"does not equal resources[].length ({len(resources)})",
        )

    # 4. Required resource types present
    actual_types = {r.get("resource_type") for r in resources}
    for rt in exp.get("required_resource_types", []):
        check(rt in actual_types, f"required resource_type '{rt}' not found in inventory")

    # 5. Required resource IDs present
    actual_ids = {r.get("resource_id") for r in resources}
    for rid in exp.get("required_resource_ids", []):
        check(rid in actual_ids, f"required resource_id '{rid}' not found in inventory")

    # 6. Every resource entry has required fields
    for r in resources:
        rid = r.get("resource_id", "<no id>")
        check("resource_id" in r, f"resource missing resource_id: {r}")
        check("resource_type" in r, f"resource {rid} missing resource_type")
        check("config" in r, f"resource {rid} missing config")
        check("mapping_status" in r, f"resource {rid} missing mapping_status")

    # 7. No forbidden clustering fields anywhere in the document
    forbidden = exp.get("forbidden_fields", [])
    if forbidden:
        check_no_forbidden_fields(inventory, "inventory", forbidden)

    # 8. No secret values (heuristic: no 'password', 'secret', 'token' values in config)
    if exp.get("no_secret_values"):
        for r in resources:
            cfg = r.get("config") or {}
            for key, val in cfg.items():
                if key.lower() in ("password", "secret", "token", "key", "credential"):
                    check(
                        val is None or val == "PLACEHOLDER_REDACTED" or str(val).startswith("ref:"),
                        f"resource {r.get('resource_id')}: config.{key} appears to contain a secret value",
                    )

    # 9. Phase status advanced to clarify
    if phase_status is not None:
        phases = phase_status.get("phases") or {}
        check(
            phases.get("discover") == "completed",
            f"phases.discover should be 'completed', got {phases.get('discover')!r}",
        )
        check(
            phase_status.get("current_phase") == "clarify",
            f"current_phase should be 'clarify', got {phase_status.get('current_phase')!r}",
        )

    if FAILS:
        _report()
        return 1
    _print_notes()
    print("PASS — expected-discover.json assertions hold")
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
