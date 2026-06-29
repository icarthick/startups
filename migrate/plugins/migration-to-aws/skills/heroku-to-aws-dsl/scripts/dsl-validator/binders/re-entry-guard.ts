// scripts/dsl-validator/binders/re-entry-guard.ts
//
// Tier-2 binder: a _re_entry_guard block -> ReEntryGuard. Shape
// `{if, action, reason, on_confirm?}` (note: BARE sub-keys, no underscore — a
// recorded grammar inconsistency). Composes bindWhenCondition (if) +
// bindErrorAction (action).

import { type ReEntryGuard } from "../types/re-entry-guard.ts";
import { type YamlValue } from "../parser/yaml.ts";
import { type Finding, type Location, type Result, error, fail, ok } from "../findings.ts";
import { isPlainObject } from "./shared.ts";
import { bindWhenCondition } from "./when-condition.ts";
import { bindErrorAction } from "./error-action.ts";

const ALLOWED = new Set(["if", "action", "reason", "on_confirm"]);

export function bindReEntryGuard(yaml: YamlValue, loc: Location): Result<ReEntryGuard> {
  if (!isPlainObject(yaml)) {
    return fail(error("BIND", `_re_entry_guard must be a {if, action, reason, on_confirm?} map`, loc));
  }
  const findings: Finding[] = [];

  for (const k of Object.keys(yaml)) {
    if (!ALLOWED.has(k)) findings.push(error("CLOSED_VOCAB", `unexpected key "${k}" in _re_entry_guard (only if, action, reason, on_confirm)`, loc));
  }

  // if -> WhenCondition
  let ifCond: ReEntryGuard["if"] | undefined;
  const rIf = bindWhenCondition(yaml.if, { ...loc, path: "if" });
  if (rIf.ok) ifCond = rIf.value;
  else findings.push(...rIf.findings);

  // action -> ErrorAction (here it is a BARE token, e.g. `action: _halt_and_inform`)
  let action: ReEntryGuard["action"] | undefined;
  const rAct = bindErrorAction(yaml.action, { ...loc, path: "action" });
  if (rAct.ok) action = rAct.value;
  else findings.push(...rAct.findings);

  // reason -> string (required)
  if (typeof yaml.reason !== "string") findings.push(error("BIND", `_re_entry_guard requires a string "reason"`, loc));

  // on_confirm? -> string | string[]
  let onConfirm: ReEntryGuard["onConfirm"] | undefined;
  if ("on_confirm" in yaml) {
    const oc = yaml.on_confirm;
    if (typeof oc === "string") onConfirm = oc;
    else if (Array.isArray(oc) && oc.every((x) => typeof x === "string")) onConfirm = oc as readonly string[];
    else findings.push(error("BIND", `on_confirm must be a string or a list of strings`, loc));
  }

  if (findings.length > 0 || ifCond === undefined || action === undefined || typeof yaml.reason !== "string") {
    if (findings.length === 0) findings.push(error("BIND", `_re_entry_guard could not be bound`, loc));
    return fail(...findings);
  }
  const base = { if: ifCond, action, reason: yaml.reason };
  return ok(onConfirm === undefined ? base : { ...base, onConfirm });
}
