#!/usr/bin/env python3
"""Assert an azure-to-aws Discover run over the azure-iac-terraform corpus.

This is the external oracle for Terraform discovery. It exists because the DSL's
`_assert` postconditions cannot verify correctness: the model both produces the
artifact and evaluates the assertion, so a run that improvises the ARM type
vocabulary from pretraining instead of consulting
`references/shared/arm-type-canonicalization.md` still produces well-formed output,
still satisfies every shape assertion, and still emits HANDOFF_OK. That output would
be labelled `confidence: deterministic`, which would be false, and two runs would
disagree.

So every check here pins a fact where a plausible improvisation and the correct
answer DIVERGE — the ARM types that are not derivable from the Terraform name
(`Microsoft.Web/sites` for a function app, the capital R in `Microsoft.Cache/Redis`,
the `DocumentDB` provider), the App Service Plan fan-in edges that prevent a 5x cost
error, the cross-resource-group edge that RG-seeded clustering needs, the routing
attributes that are the sole input to a later rubric, and the secret boundary.
Facts a model gets right by accident are deliberately NOT asserted: they cost review
attention and prove nothing.

Usage:
    python3 check_expected_iac_terraform.py <migration_run_dir>

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


def tf_name(res: dict) -> str:
    """The resource's identity: its full Terraform ADDRESS (`azurerm_subnet.data`).

    Read from provenance rather than from `name`, because a resolved Azure name may be
    an unevaluated expression (`tf:api`) and must not be relied on for identity.

    It is the ADDRESS and not `tf_resource_name`, because Terraform namespaces local
    names PER TYPE, so a bare local name is not unique. This corpus alone collides on
    five of them — `core`, `storefront`, `reporting`, `data`, `store` — and an index
    keyed on the bare name silently overwrites, which quietly points five type
    assertions at the wrong resource and makes them pass or fail by accident of
    iteration order.
    """
    return (res.get("config") or {}).get("tf_address") or ""


def by_tf_name(resources: list[dict]) -> dict[str, dict]:
    """Index by Terraform address, failing loudly on a missing or duplicate one."""
    out: dict[str, dict] = {}
    for r in resources:
        n = tf_name(r)
        if not n:
            local = (r.get("config") or {}).get("tf_resource_name") or r.get("azure_id") or "?"
            FAILS.append(
                f"{local!r}: no config.tf_address. It is the identity field — see "
                f"extract-terraform.md step 2.6; tf_resource_name alone is not unique."
            )
            continue
        if n in out:
            FAILS.append(f"duplicate config.tf_address {n!r} — addresses are unique in Terraform")
        out[n] = r
    return out


def edges_of(res: dict) -> list[dict]:
    return [e for e in (res.get("edges") or []) if isinstance(e, dict)]


def check_types(index: dict[str, dict], exp: dict) -> None:
    for local, expected_type in exp["canonical_types"].items():
        if local.startswith("_"):
            continue
        res = index.get(local)
        if res is None:
            FAILS.append(f"no inventory entry for Terraform address {local!r}")
            continue
        actual = res.get("azure_type")
        check(
            actual == expected_type,
            f"{local!r}: azure_type is {actual!r}, expected {expected_type!r} "
            f"(exact match including casing — see arm-type-canonicalization.md)",
        )


def check_forbidden_types(resources: list[dict], exp: dict) -> None:
    present = {r.get("azure_type") for r in resources}
    for bad in exp["forbidden_types"]["values"]:
        check(
            bad not in present,
            f"forbidden azure_type present: {bad!r} — not a real ARM type string, or "
            f"the wrong casing. This is the signature of a guessed translation.",
        )
    for r in resources:
        t = r.get("azure_type") or ""
        check(
            not t.startswith("azurerm_"),
            f"{tf_name(r) or '?'}: azure_type {t!r} is a Terraform type — it was never translated",
        )


def check_function_app(index: dict[str, dict], exp: dict) -> None:
    spec = exp["function_app"]
    res = index.get(spec["local_name"])
    if res is None:
        FAILS.append(f"no inventory entry for the function app {spec['local_name']!r}")
        return
    check(
        res.get("azure_type") == spec["azure_type"],
        f"function app: azure_type is {res.get('azure_type')!r}, expected "
        f"{spec['azure_type']!r} — Microsoft.Web/functionApps does not exist",
    )
    kind = ((res.get("config") or {}).get("kind") or "").lower()
    check(
        spec["kind_contains"] in kind,
        f"function app: config.kind is {kind!r} and does not contain "
        f"{spec['kind_contains']!r} — kind is the ONLY thing separating a function "
        f"app from a web app, so dropping it makes the two indistinguishable",
    )


def check_azure_ids(resources: list[dict], exp: dict) -> None:
    spec = exp["azure_id"]
    std = re.compile(spec["standard_form_regex"])
    rg = re.compile(spec["resource_group_form_regex"])
    seen: dict[str, str] = {}
    saw_placeholder = False

    for r in resources:
        aid = r.get("azure_id") or ""
        local = tf_name(r) or "?"
        if spec["subscription_placeholder"] in aid:
            saw_placeholder = True
        if aid in seen:
            FAILS.append(f"azure_id collision between {seen[aid]!r} and {local!r}: {aid}")
        seen[aid] = local

        if r.get("azure_type") == "Microsoft.Resources/resourceGroups":
            check(
                bool(rg.match(aid)),
                f"{local!r}: a resource group's own azure_id must be "
                f"/subscriptions/<s>/resourceGroups/<rg> with NO /providers/ segment, got {aid!r}",
            )
            check(
                "/providers/" not in aid,
                f"{local!r}: resource-group azure_id wrongly carries a /providers/ segment: {aid!r}",
            )
        else:
            check(
                bool(std.match(aid)),
                f"{local!r}: azure_id does not match the standard ARM form: {aid!r}",
            )

    check(
        saw_placeholder,
        f"no azure_id carries the {spec['subscription_placeholder']!r} placeholder — the "
        f"corpus's provider block declares no subscription_id, so a real GUID here means "
        f"one was invented, which makes azure_id unstable across runs and breaks drift "
        f"comparison against a live capture",
    )


def check_metadata(inv: dict, exp: dict) -> None:
    meta = inv.get("metadata") or {}
    sources = meta.get("discovery_sources")
    check(
        sources == exp["discovery_sources"],
        f"metadata.discovery_sources is {sources!r}, expected {exp['discovery_sources']!r} "
        f"— only sources that actually contributed may be listed",
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
        f"({counts['declared_in_corpus']} declared, minus the untranslated type)",
    )


def check_fan_in(index: dict[str, dict], resources: list[dict], exp: dict) -> None:
    spec = exp["app_service_plan_fan_in"]
    plan = index.get(spec["plan_local_name"])
    if plan is None:
        FAILS.append(f"no inventory entry for the App Service Plan {spec['plan_local_name']!r}")
        return

    cfg = plan.get("config") or {}
    check(
        cfg.get("sku_name") == spec["plan_sku_name"],
        f"plan config.sku_name is {cfg.get('sku_name')!r}, expected {spec['plan_sku_name']!r} "
        f"— the plan's SKU is what is being paid for",
    )
    check(
        cfg.get("worker_count") == spec["plan_worker_count"],
        f"plan config.worker_count is {cfg.get('worker_count')!r}, expected "
        f"{spec['plan_worker_count']!r} — sizing comes from the plan's instance count, "
        f"never from the number of apps",
    )

    plan_id = plan.get("azure_id")
    for key, want in (
        ("plan_local_name", spec["expected_hosted_on_edge_count"]),
        ("idle_plan_local_name", spec["idle_plan_expected_hosted_on_edge_count"]),
    ):
        target = index.get(spec[key])
        if target is None:
            FAILS.append(f"no inventory entry for plan {spec[key]!r}")
            continue
        tid = target.get("azure_id")
        n = sum(
            1
            for r in resources
            for e in edges_of(r)
            if e.get("type") == "hosted_on" and e.get("to") == tid
        )
        check(
            n == want,
            f"plan {spec[key]!r} has {n} inbound hosted_on edge(s), expected {want}. "
            f"These edges are what stop five apps on one plan from becoming five compute "
            f"line items — a 5x estimate error that is unrecoverable by Design.",
        )

    if plan_id:
        NOTES.append(f"plan {spec['plan_local_name']!r} azure_id = {plan_id}")


def check_cross_rg_edge(index: dict[str, dict], exp: dict) -> None:
    """Assert the SPECIFIC app-to-database edge, not merely that some edge crosses.

    The corpus also contains crossing subnet edges (a NIC in rg-shared into a subnet in
    rg-app). Accepting any crossing edge would let an extractor that drops the
    app-to-data reference pass, which is the one edge the horizontal-resource-group
    merge actually depends on.
    """
    spec = exp["cross_resource_group_edge"]
    src = index.get(spec["from_tf_address"])
    dst = index.get(spec["to_tf_address"])
    if src is None or dst is None:
        FAILS.append(
            f"cannot check the cross-resource-group edge: missing "
            f"{spec['from_tf_address']!r} or {spec['to_tf_address']!r}"
        )
        return

    check(
        src.get("resource_group") == spec["from_resource_group"],
        f"{spec['from_tf_address']!r} resource_group is {src.get('resource_group')!r}, "
        f"expected {spec['from_resource_group']!r}",
    )
    check(
        dst.get("resource_group") == spec["to_resource_group"],
        f"{spec['to_tf_address']!r} resource_group is {dst.get('resource_group')!r}, "
        f"expected {spec['to_resource_group']!r}",
    )

    target = dst.get("azure_id")
    match = [
        e for e in edges_of(src)
        if e.get("to") == target and e.get("type") in spec["acceptable_edge_types"]
    ]
    check(
        bool(match),
        f"no {'/'.join(spec['acceptable_edge_types'])} edge from "
        f"{spec['from_tf_address']!r} (in {spec['from_resource_group']}) to "
        f"{spec['to_tf_address']!r} (in {spec['to_resource_group']}). The app's "
        f"DATABASE_HOST setting interpolates the server's fqdn, and that edge is the "
        f"ONLY thing that later merges these two resource groups into one cluster — "
        f"resource-group seeding alone would leave the app and its database apart.",
    )
    if match:
        NOTES.append(f"app-to-data edge preserved across rg boundary: {match[0].get('type')}")


def check_private_endpoint(index: dict[str, dict], resources: list[dict], inv: dict, exp: dict) -> None:
    spec = exp["private_endpoint"]
    pe = index.get(spec["local_name"])
    if pe is None:
        FAILS.append(
            f"no inventory entry for private endpoint {spec['local_name']!r} — it must be "
            f"inventoried even though it is not a mapping target, because a resource "
            f"absent from the inventory cannot be reported as skipped"
        )
    else:
        check(
            pe.get("azure_type") == spec["azure_type"],
            f"private endpoint azure_type is {pe.get('azure_type')!r}, expected {spec['azure_type']!r}",
        )

    found = any(
        e.get("type") == spec["must_produce_edge_type"] for r in resources for e in edges_of(r)
    )
    check(
        found,
        f"no {spec['must_produce_edge_type']!r} edge anywhere — the private endpoint's "
        f"private_connection_resource_id is the explicit app-to-data edge and is the "
        f"whole reason the endpoint is read at all",
    )

    if spec["must_appear_in_warnings"]:
        warnings = json.dumps(inv.get("warnings") or [])
        check(
            spec["local_name"] in warnings or "privateEndpoint" in warnings or "private endpoint" in warnings.lower(),
            "no warnings[] entry names the consumed private endpoint — each one must be "
            "recorded with the edge it produced",
        )


def check_secrets(inv: dict, index: dict[str, dict], exp: dict) -> None:
    spec = exp["secrets"]
    blob = json.dumps(inv)
    check(
        spec["sentinel"] not in blob,
        f"the secret sentinel {spec['sentinel']!r} appears in the artifact. App-setting "
        f"values, connection strings and passwords must be DISCARDED, not recorded and "
        f"not redacted in place — a redaction placeholder still discloses that the field "
        f"existed.",
    )
    for r in inv.get("resources") or []:
        cfg = r.get("config") or {}
        for bad in spec.get("forbidden_config_keys", []):
            check(
                bad not in cfg,
                f"{tf_name(r) or '?'}: config carries {bad!r}. Values are DISCARDED, so the "
                f"container must not exist — a redaction placeholder still discloses that "
                f"the field was there and roughly how long it was, which is why asserting "
                f"only on the secret's text is not enough.",
            )

    owner = index.get(spec["app_setting_names_owner_local_name"])
    if owner is None:
        FAILS.append(f"no inventory entry for {spec['app_setting_names_owner_local_name']!r}")
        return
    names = (owner.get("config") or {}).get("app_setting_names")
    check(
        isinstance(names, list) and sorted(names) == sorted(spec["app_setting_names_expected"]),
        f"config.app_setting_names is {names!r}, expected "
        f"{sorted(spec['app_setting_names_expected'])!r} — names are kept, values never are",
    )


def check_child_rg_inheritance(index: dict[str, dict], exp: dict) -> None:
    spec = exp.get("child_resource_group_inheritance")
    if not spec:
        return
    child = index.get(spec["tf_address"])
    parent = index.get(spec["parent_tf_address"])
    if child is None or parent is None:
        FAILS.append(
            f"cannot check child resource-group inheritance: missing "
            f"{spec['tf_address']!r} or {spec['parent_tf_address']!r}"
        )
        return
    check(
        child.get("resource_group") == spec["expected_resource_group"],
        f"{spec['tf_address']!r} resource_group is {child.get('resource_group')!r}, expected "
        f"{spec['expected_resource_group']!r}. It declares no resource_group_name and must "
        f"inherit its parent's via the storage_account_id reference — a null group cannot "
        f"be clustered, and most child resources in a real estate look like this.",
    )
    check(
        child.get("resource_group") == parent.get("resource_group"),
        f"{spec['tf_address']!r} resource_group {child.get('resource_group')!r} does not match "
        f"its parent {spec['parent_tf_address']!r} ({parent.get('resource_group')!r})",
    )

def check_warnings(inv: dict, exp: dict) -> None:
    warnings = json.dumps(inv.get("warnings") or []) + json.dumps(inv.get("iac_metadata") or {})
    for t in exp["untranslated_types"]["expected"]:
        check(
            t in warnings,
            f"{t!r} is absent from arm-type-canonicalization.md and must be reported as "
            f"untranslated. Guessing an ARM type for it would not fail loudly — it would "
            f"silently miss every mapping table, and the report would blame the estate "
            f"for the skill's gap.",
        )
    sub = exp["unresolved_modules"]["expected_substring"]
    check(
        sub in warnings,
        f"no warning names the unresolvable module {sub!r}. A registry module whose "
        f"content is not in the workspace is the commonest reason a Terraform-only "
        f"inventory is confidently incomplete.",
    )


def check_discriminators(index: dict[str, dict], exp: dict) -> None:
    for label, spec in exp["routing_discriminators"].items():
        if label.startswith("_"):
            continue
        res = index.get(spec["local_name"])
        if res is None:
            FAILS.append(f"no inventory entry for {spec['local_name']!r} ({label})")
            continue
        actual = (res.get("config") or {}).get(spec["config_key"])
        check(
            actual == spec["value"],
            f"{label}: config.{spec['config_key']} is {actual!r}, expected {spec['value']!r}. "
            f"This attribute is the SOLE input to a later rubric decision — dropping it "
            f"fails no shape assertion, it just makes the rubric guess.",
        )


def check_no_terraform_leakage(inv: dict, exp: dict) -> None:
    # tf_file / tf_resource_name are legitimate provenance, so scan azure_type only.
    for r in inv.get("resources") or []:
        for bad in exp["forbidden_artifact_substrings"]["values"]:
            t = r.get("azure_type") or ""
            check(
                bad not in t,
                f"{tf_name(r) or '?'}: azure_type {t!r} contains {bad!r}",
            )


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    run_dir = Path(sys.argv[1])

    exp = load(HERE / "expected-iac-terraform.json")
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

    index = by_tf_name(resources)

    check_metadata(inv, exp)
    check_types(index, exp)
    check_forbidden_types(resources, exp)
    check_function_app(index, exp)
    check_azure_ids(resources, exp)
    check_fan_in(index, resources, exp)
    check_cross_rg_edge(index, exp)
    check_private_endpoint(index, resources, inv, exp)
    check_secrets(inv, index, exp)
    check_child_rg_inheritance(index, exp)
    check_warnings(inv, exp)
    check_discriminators(index, exp)
    check_no_terraform_leakage(inv, exp)

    if FAILS:
        _report()
        return 1
    _print_notes()
    print("PASS — expected-iac-terraform.json assertions hold")
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
