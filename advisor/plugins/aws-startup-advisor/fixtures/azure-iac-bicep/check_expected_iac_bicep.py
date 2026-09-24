#!/usr/bin/env python3
"""Assert an azure-to-aws Discover run over the azure-iac-bicep corpus.

This is the external oracle for Bicep discovery. It exists for the same reason as
check_expected_iac_terraform.py: the DSL's _assert postconditions cannot verify
correctness. The model both produces the artifact and evaluates the assertion, so a
run that improvises Bicep semantics from pretraining instead of reading
references/shared/extract-bicep.md still produces well-formed output and emits
HANDOFF_OK. Only a Python asserter is unbypassable.

Bicep-specific assertions (beyond what the Terraform asserter also checks):
  - api_version stripped from azure_type (no '@' present)
  - config.bicep_api_version carries the stripped version
  - source: "bicep" on every entry
  - 'existing' resource carries config.bicep_existing: true
  - loop resource produces ONE entry with config.multiplicity_unresolved: true
  - local module resource carries config.bicep_module
  - registry module NOT on disk produces a module_not_resolved warning
  - symbolic-ref edges resolve to correct azure_id targets
  - secret sentinel absent from artifact; app_setting_names contains keys, not values

Usage:
    python3 check_expected_iac_bicep.py <migration_run_dir>

Exits 0 on PASS, 1 on FAIL. Stdlib only.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
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


def bicep_addr(res: dict) -> str:
    """Return the resource's bicep_address — its identity in this asserter."""
    return (res.get("config") or {}).get("bicep_address") or ""


def by_bicep_addr(resources: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in resources:
        addr = bicep_addr(r)
        if not addr:
            local = (r.get("config") or {}).get("bicep_symbol") or r.get("azure_id") or "?"
            FAILS.append(
                f"{local!r}: no config.bicep_address. It is the identity field for Bicep resources."
            )
            continue
        if addr in out:
            FAILS.append(f"duplicate config.bicep_address {addr!r}")
        out[addr] = r
    return out


def edges_of(res: dict) -> list[dict]:
    return [e for e in (res.get("edges") or []) if isinstance(e, dict)]


def check_types(index: dict[str, dict], exp: dict) -> None:
    for addr, expected_type in exp["canonical_types"].items():
        if addr.startswith("_"):
            continue
        res = index.get(addr)
        if res is None:
            FAILS.append(f"no inventory entry for bicep_address {addr!r}")
            continue
        actual = res.get("azure_type")
        check(
            actual == expected_type,
            f"{addr!r}: azure_type is {actual!r}, expected {expected_type!r}",
        )


def check_api_version_stripped(index: dict[str, dict], exp: dict) -> None:
    spec = exp.get("api_version_stripped") or {}
    for addr, rule in spec.items():
        if addr.startswith("_"):
            continue
        res = index.get(addr)
        if res is None:
            FAILS.append(f"api_version check: no entry for {addr!r}")
            continue
        azure_type = res.get("azure_type") or ""
        check(
            "@" not in azure_type,
            f"{addr!r}: azure_type {azure_type!r} contains '@' — the api-version suffix was "
            f"not stripped. azure_type must be the bare ARM type string without any "
            f"'@YYYY-MM-DD' suffix.",
        )
        cfg = res.get("config") or {}
        expected_ver = rule.get("expected_bicep_api_version")
        actual_ver = cfg.get("bicep_api_version")
        check(
            actual_ver == expected_ver,
            f"{addr!r}: config.bicep_api_version is {actual_ver!r}, expected {expected_ver!r}. "
            f"The version suffix stripped from the type string must be carried in this field.",
        )


def check_source_field(resources: list[dict], exp: dict) -> None:
    expected_source = exp["source_field"]["expected_source"]
    for r in resources:
        addr = bicep_addr(r) or r.get("azure_id") or "?"
        actual = r.get("source")
        check(
            actual == expected_source,
            f"{addr!r}: source is {actual!r}, expected {expected_source!r}. "
            f"Every Bicep-sourced resource must carry source:bicep.",
        )


def check_existing_keyword(index: dict[str, dict], exp: dict) -> None:
    spec = exp.get("existing_keyword")
    if not spec:
        return
    addr = spec["bicep_address"]
    res = index.get(addr)
    if res is None:
        FAILS.append(
            f"no inventory entry for {addr!r} — an 'existing' resource must be inventoried. "
            f"A resource absent from the inventory cannot be reported as a dependency "
            f"the workload has."
        )
        return
    cfg = res.get("config") or {}
    key = spec["expected_config_key"]
    val = spec["expected_config_value"]
    check(
        cfg.get(key) == val,
        f"{addr!r}: config.{key} is {cfg.get(key)!r}, expected {val!r}. "
        f"A resource declared with the Bicep 'existing' keyword must carry this flag so "
        f"downstream phases know it was pre-existing, not deployed by this template.",
    )


def check_loop_resource(index: dict[str, dict], resources: list[dict], exp: dict) -> None:
    spec = exp.get("loop_resource")
    if not spec:
        return
    addr = spec["bicep_address"]
    loop_entries = [r for r in resources if bicep_addr(r) == addr]
    check(
        len(loop_entries) == 1,
        f"loop resource {addr!r}: found {len(loop_entries)} inventory entries, expected 1. "
        f"A Bicep for-expression produces ONE inventory entry — fanning out invents resources.",
    )
    res = index.get(addr)
    if res is None:
        return
    cfg = res.get("config") or {}
    check(
        cfg.get("multiplicity_unresolved") is True,
        f"{addr!r}: config.multiplicity_unresolved is {cfg.get('multiplicity_unresolved')!r}, "
        f"expected true. The for-expression count is unresolved at static-analysis time.",
    )


def check_local_module(index: dict[str, dict], exp: dict) -> None:
    spec = exp.get("local_module")
    if not spec:
        return
    addr = spec["bicep_address"]
    res = index.get(addr)
    if res is None:
        FAILS.append(
            f"no inventory entry for {addr!r}. It lives in a local module "
            f"({spec.get('expected_bicep_file', '?')}) that is on disk and must be "
            f"recursed into."
        )
        return
    cfg = res.get("config") or {}
    expected_module = spec["expected_bicep_module"]
    actual_module = cfg.get("bicep_module")
    check(
        actual_module == expected_module,
        f"{addr!r}: config.bicep_module is {actual_module!r}, expected {expected_module!r}. "
        f"Resources from a local module must carry the module address for provenance.",
    )
    expected_file = spec["expected_bicep_file"]
    actual_file = cfg.get("bicep_file")
    check(
        actual_file == expected_file,
        f"{addr!r}: config.bicep_file is {actual_file!r}, expected {expected_file!r}.",
    )


def check_symbolic_ref_edges(index: dict[str, dict], exp: dict) -> None:
    spec = exp.get("symbolic_ref_edges") or {}
    for label, rule in spec.items():
        if label.startswith("_"):
            continue
        from_addr = rule["from_bicep_address"]
        to_addr = rule["to_bicep_address"]
        edge_type = rule["expected_edge_type"]
        via_contains = rule.get("via_contains", "")

        src = index.get(from_addr)
        dst = index.get(to_addr)
        if src is None or dst is None:
            FAILS.append(
                f"symbolic-ref edge {label!r}: missing {from_addr!r} or {to_addr!r}"
            )
            continue

        target_id = dst.get("azure_id")
        matches = [
            e for e in edges_of(src)
            if e.get("type") == edge_type and e.get("to") == target_id
        ]
        check(
            bool(matches),
            f"symbolic-ref edge {label!r}: no {edge_type!r} edge from {from_addr!r} to "
            f"{to_addr!r} (azure_id={target_id!r}). Bicep symbolic references must resolve "
            f"to the target's azure_id.",
        )
        if via_contains and matches:
            check(
                any(via_contains in (e.get("via") or "") for e in matches),
                f"symbolic-ref edge {label!r}: edge found but via does not contain "
                f"{via_contains!r}. The 'via' field names the Bicep property the edge came "
                f"from — without it the Clarify assumption sheet cannot explain the relationship.",
            )
        if matches:
            NOTES.append(f"{label} edge: {from_addr} →[{edge_type}]→ {to_addr}")


def check_secrets(inv: dict, index: dict[str, dict], exp: dict) -> None:
    spec = exp.get("secrets")
    if not spec:
        return
    blob = json.dumps(inv)
    check(
        spec["sentinel"] not in blob,
        f"the secret sentinel {spec['sentinel']!r} appears in the artifact. App-setting "
        f"values must be DISCARDED, not recorded and not redacted in place.",
    )
    owner = index.get(spec["app_setting_names_owner_bicep_address"])
    if owner is None:
        FAILS.append(f"no inventory entry for {spec['app_setting_names_owner_bicep_address']!r}")
        return
    names = (owner.get("config") or {}).get("app_setting_names")
    check(
        isinstance(names, list) and sorted(names) == sorted(spec["app_setting_names_expected"]),
        f"config.app_setting_names is {names!r}, expected "
        f"{sorted(spec['app_setting_names_expected'])!r} — names are kept, values never are",
    )


def check_registry_module_warning(inv: dict, exp: dict) -> None:
    spec = exp.get("registry_module_warning")
    if not spec:
        return
    warnings = inv.get("warnings") or []
    code = spec["expected_warning_code"]
    substr = spec["expected_identifier_substring"]
    found = any(
        w.get("code") == code and (
            substr in (w.get("identifier") or "")
            or substr in (w.get("detail") or "")
        )
        for w in warnings
    )
    check(
        found,
        f"no {code!r} warning naming {substr!r}. A registry module not on disk must produce "
        f"a module_not_resolved warning — its resources were not discovered, and silence "
        f"implies a complete inventory.",
    )


def check_metadata(inv: dict, exp: dict) -> None:
    meta = inv.get("metadata") or {}
    sources = meta.get("discovery_sources")
    check(
        sources == exp["discovery_sources"],
        f"metadata.discovery_sources is {sources!r}, expected {exp['discovery_sources']!r}",
    )
    iac = inv.get("iac_metadata") or {}
    want = exp["azure_id"]["subscription_id_source"]
    check(
        iac.get("subscription_id_source") == want,
        f"iac_metadata.subscription_id_source is {iac.get('subscription_id_source')!r}, "
        f"expected {want!r}",
    )
    counts = exp["resource_counts"]
    actual = len(inv.get("resources") or [])
    check(
        actual == counts["expected_in_inventory"],
        f"inventory has {actual} resources, expected {counts['expected_in_inventory']} "
        f"({counts['declared_in_corpus']} declared in corpus).",
    )


def check_azure_ids(resources: list[dict], exp: dict) -> None:
    spec = exp["azure_id"]
    std = re.compile(spec["standard_form_regex"])
    seen: dict[str, str] = {}
    saw_placeholder = False

    for r in resources:
        aid = r.get("azure_id") or ""
        addr = bicep_addr(r) or "?"
        if spec["subscription_placeholder"] in aid:
            saw_placeholder = True
        if aid in seen:
            FAILS.append(f"azure_id collision between {seen[aid]!r} and {addr!r}: {aid}")
        seen[aid] = addr

        if r.get("azure_type") != "Microsoft.Resources/resourceGroups":
            if "bicep:" not in aid:
                check(
                    bool(std.match(aid)),
                    f"{addr!r}: azure_id does not match the standard ARM form: {aid!r}",
                )

    check(
        saw_placeholder,
        f"no azure_id carries the {spec['subscription_placeholder']!r} placeholder — "
        f"Bicep templates never carry the subscription ID, so the placeholder is always "
        f"required for a static extraction.",
    )


def check_contract_vocabulary(inv: dict, exp: dict) -> None:
    spec = exp.get("contract_vocabulary")
    if not spec:
        return

    allowed_codes = set(spec["warning_codes"])
    warnings = inv.get("warnings")
    if not isinstance(warnings, list):
        FAILS.append("inventory has no top-level warnings[] array.")
    else:
        for w in warnings:
            code = w.get("code")
            check(
                code in allowed_codes,
                f"warning code {code!r} is not in the closed vocabulary {sorted(allowed_codes)}.",
            )
            for k in ("code", "detail"):
                check(bool(w.get(k)), f"warning {code!r} has no {k!r}")
            check(
                bool(w.get("azure_id")) or bool(w.get("identifier")),
                f"warning {code!r} has neither 'azure_id' nor 'identifier'",
            )

    allowed_edges = set(spec["edge_types"])
    for r in inv.get("resources") or []:
        for e in edges_of(r):
            check(
                e.get("type") in allowed_edges,
                f"{bicep_addr(r) or '?'}: edge type {e.get('type')!r} is not in the "
                f"canonical set {sorted(allowed_edges)}.",
            )

    if spec.get("forbid_null_config_values"):
        for r in inv.get("resources") or []:
            for k, v in (r.get("config") or {}).items():
                check(
                    v is not None,
                    f"{bicep_addr(r) or '?'}: config.{k} is null — omit, do not null.",
                )


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    run_dir = Path(sys.argv[1])

    exp = load(HERE / "expected-iac-bicep.json")
    if exp is None:
        _report()
        return 1

    inv = load(run_dir / exp["inventory_file"])
    if inv is None:
        _report()
        return 1

    resources = inv.get("resources") or []
    if not isinstance(resources, list) or not resources:
        FAILS.append("inventory resources[] is missing or empty")
        _report()
        return 1

    index = by_bicep_addr(resources)

    check_metadata(inv, exp)
    check_types(index, exp)
    check_api_version_stripped(index, exp)
    check_source_field(resources, exp)
    check_existing_keyword(index, exp)
    check_loop_resource(index, resources, exp)
    check_local_module(index, exp)
    check_symbolic_ref_edges(index, exp)
    check_secrets(inv, index, exp)
    check_registry_module_warning(inv, exp)
    check_azure_ids(resources, exp)
    check_contract_vocabulary(inv, exp)

    if FAILS:
        _report()
        return 1
    _print_notes()
    print("PASS — expected-iac-bicep.json assertions hold")
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
