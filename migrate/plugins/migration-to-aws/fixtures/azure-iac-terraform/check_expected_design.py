#!/usr/bin/env python3
"""Assert an azure-to-aws Design run (pass 1) over the azure-iac-terraform corpus.

The external oracle for the mapping algorithm, and the companion to
check_expected_iac_terraform.py. It exists for the same reason: the DSL's `_assert`
postconditions verify SHAPE, never correctness, and the model both produces
`aws-design.json` and evaluates the assertions against it. A design that routes a
Mongo-API Cosmos account to DynamoDB, an SMB share to EFS, and a Kafka-enabled Event
Hubs namespace to Kinesis is well-formed, satisfies every postcondition, and is wrong
in three places that each cost a rewrite.

Every check pins a fact where a plausible improvisation and the correct answer DIVERGE:

  * the three protocol/API-conditioned Direct Mappings rows, each of which has a
    famous wrong answer (DynamoDB, EFS, Kinesis);
  * the App Service Plan fan-in, where a per-app mapping is a 5x estimate error;
  * the untranslated cost-bearing type, where warn-and-skip is the silent failure;
  * the `deterministic` label itself, checked in BOTH directions against the table;
  * the table's own row set, because a design is only as trustworthy as the rows it
    claims to have read.

Facts a model gets right by accident are deliberately NOT asserted.

Identity is the Terraform ADDRESS, resolved to an `azure_id` through the run's own
inventory. Design artifacts key on `azure_id`, but most Terraform-sourced ids in this
corpus carry a synthetic `tf:<local>` name segment (every resource is named with
${var.prefix}), so hard-coding them here would couple these expectations to an id
reconstruction that is expected to change when the live `az` path lands.

Usage:
    python3 check_expected_design.py <migration_run_dir>

Exits 0 on PASS, 1 on FAIL. Stdlib only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FAILS: list[str] = []
NOTES: list[str] = []

SERVERFARMS = "Microsoft.Web/serverfarms"
SITES = "Microsoft.Web/sites"


def check(cond: bool, msg: str) -> None:
    if not cond:
        FAILS.append(msg)


def load(path: Path, label: str) -> dict | None:
    if not path.exists():
        FAILS.append(f"missing {label} at {path}")
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        FAILS.append(f"{label} is not valid JSON: {e}")
        return None


def real_keys(d: dict) -> list[str]:
    """Table keys, minus the leading-underscore documentation keys."""
    return [k for k in d if not k.startswith("_")]


# --------------------------------------------------------------------------- table


def check_table(table: dict, exp: dict) -> None:
    """Validate the disposition table itself, before trusting a design that cites it.

    A design row saying `confidence: deterministic, fast_path_row: X` is only
    meaningful if X exists. And the precedence order is only coherent if a type
    resolves to at most one disposition.
    """
    spec = exp["table_self_checks"]
    direct = table.get("direct_mappings") or {}
    skips = table.get("skip_mappings") or {}
    gates = table.get("specialist_gates") or {}

    for t in spec["required_direct_rows"]:
        check(
            t in direct,
            f"direct_mappings has no row for {t!r}. {spec['_required_direct_rows_why']}",
        )
    for t in spec["must_not_be_direct_rows"]:
        check(
            t not in direct,
            f"{t!r} is a direct_mappings row and must not be. "
            f"{spec['_must_not_be_direct_rows_why']}",
        )
    for t in spec["required_skip_rows"]:
        check(t in skips, f"skip_mappings has no row for {t!r}")
    for t in spec["required_gate_rows"]:
        check(t in gates, f"specialist_gates has no row for {t!r}")

    # Precedence invariant: at most one disposition per canonical type. A conditional
    # gate key carries a '#suffix' (Microsoft.Compute/virtualMachines#sql_on_vm) and is
    # deliberately exempt — it fires on config, not on the type, so the base type
    # legitimately also lives on the rubric path.
    seen: dict[str, str] = {}
    for label, tbl in (("direct_mappings", direct), ("skip_mappings", skips), ("specialist_gates", gates)):
        for t in real_keys(tbl):
            if "#" in t:
                continue
            if t in seen:
                FAILS.append(
                    f"{t!r} appears in both {seen[t]} and {label}. A canonical type must "
                    f"resolve to AT MOST ONE disposition — two makes the precedence order "
                    f"depend on iteration order rather than on the documented sequence."
                )
            seen[t] = label

    banned = spec["banned_substring"]
    check(
        banned not in json.dumps(table),
        f"{banned!r} appears in the disposition table. {spec['_banned_substring_why']}",
    )
    NOTES.append(f"table: {len(real_keys(direct))} direct, {len(real_keys(skips))} skip, {len(real_keys(gates))} gate rows")


# ---------------------------------------------------------------------- design body


def entries(design: dict) -> list[dict]:
    """Every per-resource entry, whatever section it landed in."""
    out: list[dict] = []
    for section in ("services", "pending_rubric", "deferred"):
        for e in design.get(section) or []:
            if isinstance(e, dict):
                out.append({**e, "_section": section})
    return out


def check_deterministic(design: dict, table: dict, id_of: dict[str, str], exp: dict) -> None:
    direct = table.get("direct_mappings") or {}
    services = {e.get("azure_id"): e for e in (design.get("services") or []) if isinstance(e, dict)}
    want_label = exp["confidence"]["expected_value"]

    for tf_addr, spec in exp["deterministic_mappings"].items():
        if tf_addr.startswith("_"):
            continue
        aid = id_of.get(tf_addr)
        if aid is None:
            FAILS.append(f"no inventory resource with Terraform address {tf_addr!r} — cannot check its mapping")
            continue
        e = services.get(aid)
        if e is None:
            FAILS.append(
                f"{tf_addr!r}: no services[] entry. It matches a Direct Mappings row, so it "
                f"must be mapped rather than deferred, skipped, or left pending."
            )
            continue

        got = e.get("aws_service")
        check(
            got == spec["aws_service"],
            f"{tf_addr!r}: aws_service is {got!r}, expected {spec['aws_service']!r}."
            + (f" {spec['why']}" if spec.get("why") else ""),
        )
        for bad in spec.get("must_not_be", []):
            check(
                got != bad,
                f"{tf_addr!r}: aws_service is {bad!r}, which is the plausible-but-wrong answer. "
                + (spec.get("why") or ""),
            )
        check(
            e.get("confidence") == want_label,
            f"{tf_addr!r}: confidence is {e.get('confidence')!r}, expected {want_label!r} — it "
            f"came from a table row, so no rubric ran.",
        )

    # The direction that catches a fabricated label: anything claiming `deterministic`
    # must name a type that really is in the table, with a target the row allows.
    for e in design.get("services") or []:
        if e.get("confidence") != want_label:
            continue
        t = e.get("azure_type")
        row = direct.get(t)
        if row is None:
            FAILS.append(
                f"{t!r} is labelled {want_label!r} but has NO direct_mappings row. This is the "
                f"signature of an improvised label: the target may even be reasonable, but it "
                f"came from a prior rather than a table, so it is unreproducible and the "
                f"user-facing 'Standard pairing' claim is false."
            )
            continue
        allowed = {row.get("aws_service")} | {a.get("aws_service") for a in (row.get("alternatives") or [])}
        check(
            e.get("aws_service") in allowed,
            f"{t!r} is labelled {want_label!r} with aws_service {e.get('aws_service')!r}, which "
            f"is not the row's target or any of its alternatives ({sorted(x for x in allowed if x)}).",
        )
        check(
            e.get("confidence") in exp["confidence"]["allowed_values"],
            f"{t!r}: confidence {e.get('confidence')!r} is not one of {exp['confidence']['allowed_values']}",
        )


def check_fan_in(design: dict, inv: dict, id_of: dict[str, str], exp: dict) -> None:
    spec = exp["app_service_plan_fan_in"]
    all_entries = entries(design)

    plans = [e for e in all_entries if e.get("azure_type") == SERVERFARMS]
    check(
        len(plans) == spec["expected_compute_unit_count"],
        f"{len(plans)} {SERVERFARMS} entr(ies), expected {spec['expected_compute_unit_count']} — "
        f"one compute unit per PLAN. {spec['_why']}",
    )

    sites = [e for e in all_entries if e.get("azure_type") == SITES]
    check(
        len(sites) == spec["expected_site_entry_count"],
        f"{len(sites)} {SITES} entr(ies) in services[]/pending_rubric[]/deferred[], expected "
        f"{spec['expected_site_entry_count']}. {spec['_expected_site_entry_count_why']} "
        f"{spec['_why']}",
    )

    by_id = {e.get("azure_id"): e for e in all_entries}
    for key, want_count in (
        ("web_plan_tf_address", spec["web_plan_expected_hosted_app_count"]),
        ("idle_plan_tf_address", spec["idle_plan_expected_hosted_app_count"]),
    ):
        aid = id_of.get(spec[key])
        plan = by_id.get(aid)
        if plan is None:
            FAILS.append(f"no design entry for plan {spec[key]!r}")
            continue
        hosted = plan.get("hosted_app_azure_ids")
        if hosted is None:
            FAILS.append(
                f"plan {spec[key]!r} has no hosted_app_azure_ids. It is the record of WHICH apps "
                f"fanned in; without it the one-compute-unit-per-plan rule cannot be audited, and "
                f"an app silently dropped from the plan's aws_config is undetectable."
            )
            continue
        check(
            len(hosted) == want_count,
            f"plan {spec[key]!r} lists {len(hosted)} hosted app(s), expected {want_count}. "
            f"{spec['_why']}",
        )
        known = set(id_of.values())
        for h in hosted:
            check(h in known, f"plan {spec[key]!r} lists hosted app {h!r}, which is not in the inventory")

    web = by_id.get(id_of.get(spec["web_plan_tf_address"]))
    if web is not None:
        sizing = web.get("sizing_source") or web.get("aws_config") or {}
        check(
            sizing.get("sku_name") == spec["web_plan_expected_sku"],
            f"web plan sku is {sizing.get('sku_name')!r}, expected {spec['web_plan_expected_sku']!r} "
            f"— sizing comes from the plan's SKU, never from the app count",
        )
        check(
            sizing.get("worker_count") == spec["web_plan_expected_worker_count"],
            f"web plan worker_count is {sizing.get('worker_count')!r}, expected "
            f"{spec['web_plan_expected_worker_count']!r}",
        )

    warnings = design.get("warnings") or []
    consumed = [w for w in warnings if w.get("code") == spec["consumed_app_warning_code"]]
    check(
        len(consumed) == spec["expected_consumed_app_count"],
        f"{len(consumed)} {spec['consumed_app_warning_code']!r} warning(s), expected "
        f"{spec['expected_consumed_app_count']} — one per app consumed by a plan. Every site must "
        f"be accounted for; an app with no entry and no warning is indistinguishable from one the "
        f"design forgot.",
    )

    idle_aid = id_of.get(spec["idle_plan_tf_address"])
    check(
        any(w.get("code") == spec["idle_plan_warning_code"] and w.get("azure_id") == idle_aid for w in warnings),
        f"no {spec['idle_plan_warning_code']!r} warning for {spec['idle_plan_tf_address']!r}. A plan "
        f"with zero apps is purchased capacity with no workload — money already being spent, and a "
        f"cost-optimization finding the customer cannot get anywhere else.",
    )


def check_unknown_stop(design: dict, exp: dict) -> None:
    spec = exp["unknown_type_stop"]
    halt = design.get("halt")
    if not isinstance(halt, dict):
        FAILS.append(
            f"no `halt` object. The corpus contains an untranslated type "
            f"({spec['expected_identifier_substring']}), which is treated as cost-bearing and must "
            f"STOP the design. {spec['_why']}"
        )
        return

    blocking = halt.get("blocking") or []
    hit = [
        b for b in blocking
        if b.get("kind") == spec["expected_halt_kind"]
        and spec["expected_identifier_substring"] in json.dumps(b)
    ]
    check(
        bool(hit),
        f"halt.blocking has no {spec['expected_halt_kind']!r} entry naming "
        f"{spec['expected_identifier_substring']!r}. {spec['_why']}",
    )

    for w in design.get("warnings") or []:
        if w.get("code") in spec["must_not_appear_as_benign_skip_codes"]:
            check(
                spec["expected_identifier_substring"] not in json.dumps(w),
                f"{spec['expected_identifier_substring']!r} is recorded as a benign skip "
                f"({w.get('code')!r}) instead of stopping the design. "
                f"{spec['_must_not_appear_why']}",
            )


def check_pending_rubric(design: dict, id_of: dict[str, str], exp: dict) -> None:
    spec = exp["missing_rubric_halt"]
    pending = {e.get("azure_id"): e for e in (design.get("pending_rubric") or []) if isinstance(e, dict)}
    services = {e.get("azure_id") for e in (design.get("services") or []) if isinstance(e, dict)}

    for tf_addr in spec["expected_pending_rubric_tf_addresses"]:
        aid = id_of.get(tf_addr)
        if aid is None:
            FAILS.append(f"no inventory resource with Terraform address {tf_addr!r}")
            continue
        e = pending.get(aid)
        if e is None:
            FAILS.append(
                f"{tf_addr!r} is not in pending_rubric[]. index.md routes it to a category file "
                f"that does not exist yet, so it must be recorded as pending, not mapped. "
                f"{spec['_why']}"
            )
            continue
        check(
            bool(e.get("ref_file")),
            f"{tf_addr!r}: pending_rubric entry names no ref_file, so a reader cannot tell which "
            f"rubric is missing",
        )

    for tf_addr in spec["must_not_be_in_services"]:
        aid = id_of.get(tf_addr)
        check(
            aid not in services,
            f"{tf_addr!r} has a services[] entry, but its rubric file does not exist on disk. "
            f"That mapping was improvised. {spec['_why']}",
        )

    halt = design.get("halt") or {}
    check(
        any(b.get("kind") == spec["expected_halt_kind"] for b in (halt.get("blocking") or [])),
        f"halt.blocking has no {spec['expected_halt_kind']!r} entry, yet pass-2 rubric files are "
        f"absent. A design that quietly maps around a missing rubric reads as complete.",
    )


def check_skips(design: dict, id_of: dict[str, str], exp: dict) -> None:
    spec = exp["skips"]
    warnings = design.get("warnings") or []
    mapped = {e.get("azure_id") for e in entries(design)}
    blob_by_id: dict[str, str] = {}
    for w in warnings:
        aid = w.get("azure_id")
        if aid:
            blob_by_id[aid] = blob_by_id.get(aid, "") + json.dumps(w)

    for tf_addr in spec["expected_skipped_tf_addresses"]:
        aid = id_of.get(tf_addr)
        if aid is None:
            FAILS.append(f"no inventory resource with Terraform address {tf_addr!r}")
            continue
        check(
            aid in blob_by_id,
            f"{tf_addr!r} is a Skip Mapping but has no warnings[] entry. A resource with no entry "
            f"and no warning is indistinguishable from one the design forgot.",
        )
        check(
            aid not in mapped,
            f"{tf_addr!r} is a Skip Mapping but was given a target. Observability in particular has "
            f"no import path, so a CloudWatch TARGET would claim a migration that cannot happen — "
            f"the CloudWatch fallback is a report note, not a mapping.",
        )

    for tf_addr in spec["config_source_tf_addresses"]:
        aid = id_of.get(tf_addr)
        blob = blob_by_id.get(aid, "")
        check(
            "config_source" in blob or "consumed" in blob or "edge" in blob,
            f"{tf_addr!r} is a CONFIG SOURCE skip, but its warning does not say what it "
            f"contributed. {spec['_config_source_why']}",
        )


def check_hard_blocker(design: dict, id_of: dict[str, str], exp: dict) -> None:
    spec = exp["hard_blocker"]
    aid = id_of.get(spec["tf_address"])
    hit = [
        w for w in (design.get("warnings") or [])
        if w.get("code") == spec["expected_warning_code"] and w.get("azure_id") == aid
    ]
    check(
        bool(hit),
        f"no {spec['expected_warning_code']!r} warning for {spec['tf_address']!r}. {spec['_why']}",
    )
    if hit:
        check(
            hit[0].get("severity") == spec["expected_severity"],
            f"{spec['expected_warning_code']!r} severity is {hit[0].get('severity')!r}, expected "
            f"{spec['expected_severity']!r} — MGN refuses the image, so this is not advisory",
        )


def check_deferred_shape(design: dict, exp: dict) -> None:
    spec = exp["deferred_shape"]
    deferred = design.get("deferred") or []
    for d in deferred:
        check(
            d.get("aws_service") == spec["expected_aws_service"],
            f"deferred entry aws_service is {d.get('aws_service')!r}, expected "
            f"{spec['expected_aws_service']!r}",
        )
        check(
            spec["forbidden_field"] not in d,
            f"deferred entry carries a {spec['forbidden_field']!r} field. {spec['_why']}",
        )
    if not deferred:
        NOTES.append("deferred[] is empty — no specialist gate fires on this corpus (expected)")


def check_accounting(design: dict, inv: dict, id_of: dict[str, str], exp: dict) -> None:
    spec = exp["accounting"]
    n = len(inv.get("resources") or [])
    check(
        n == spec["expected_inventory_resource_count"],
        f"the run's inventory has {n} resources, expected "
        f"{spec['expected_inventory_resource_count']} — the design is being checked against the "
        f"wrong inventory",
    )

    accounted = {e.get("azure_id") for e in entries(design)}
    warned = {w.get("azure_id") for w in (design.get("warnings") or []) if w.get("azure_id")}
    accounted |= warned

    for tf_addr, aid in id_of.items():
        check(
            aid in accounted,
            f"{tf_addr!r} appears NOWHERE in the design — not mapped, not pending, not deferred, "
            f"not skipped. {spec['_why']}",
        )


def check_forbidden(design: dict, exp: dict) -> None:
    blob = json.dumps(design)
    for bad in exp["forbidden_substrings"]["values"]:
        check(
            bad not in blob,
            f"{bad!r} appears in aws-design.json. {exp['forbidden_substrings']['_why']}",
        )


# ---------------------------------------------------------------------------- main


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    run_dir = Path(sys.argv[1])

    exp = load(HERE / "expected-design.json", "expected-design.json")
    if exp is None:
        _report()
        return 1

    design = load(run_dir / exp["design_file"], exp["design_file"])
    if design is None:
        _report()
        return 1

    inv_path = run_dir / exp["inventory_file"]
    if not inv_path.exists():
        # The golden design tree does not duplicate the 23k inventory. A REAL run always
        # has both in the same directory; this fallback exists only so the committed
        # golden tree can be checked without a second copy of the same bytes.
        inv_path = HERE / "after-discover" / exp["inventory_file"]
        NOTES.append(f"no inventory in the run dir; using the fixture's own golden at {inv_path.name}")
    inv = load(inv_path, exp["inventory_file"])
    if inv is None:
        _report()
        return 1

    table = load(HERE / exp["fast_path_table_relpath"], "fast-path-services.json")
    if table is None:
        _report()
        return 1

    # tf_address -> azure_id, from the inventory the design was built from.
    id_of: dict[str, str] = {}
    for r in inv.get("resources") or []:
        addr = (r.get("config") or {}).get("tf_address")
        aid = r.get("azure_id")
        if addr and aid:
            id_of[addr] = aid
    if not id_of:
        FAILS.append("no resource in the inventory carries config.tf_address — cannot resolve identity")
        _report()
        return 1

    check_table(table, exp)
    check_deterministic(design, table, id_of, exp)
    check_fan_in(design, inv, id_of, exp)
    check_unknown_stop(design, exp)
    check_pending_rubric(design, id_of, exp)
    check_skips(design, id_of, exp)
    check_hard_blocker(design, id_of, exp)
    check_deferred_shape(design, exp)
    check_accounting(design, inv, id_of, exp)
    check_forbidden(design, exp)

    if FAILS:
        _report()
        return 1
    _print_notes()
    print("PASS — expected-design.json assertions hold")
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
