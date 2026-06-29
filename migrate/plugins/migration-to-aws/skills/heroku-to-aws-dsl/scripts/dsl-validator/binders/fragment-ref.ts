// scripts/dsl-validator/binders/fragment-ref.ts
//
// Tier-2 binder: a _fragments entry -> FragmentRef. Shape `{_id, _trigger, _file}`.
// `_trigger` is a single-key map (e.g. { _glob: ... }) — unwrap it and bind via
// bindTrigger.

import { type FragmentRef } from "../types/fragment-ref.ts";
import { type YamlValue } from "../parser/yaml.ts";
import { type Finding, type Location, type Result, error, fail, ok } from "../findings.ts";
import { isPlainObject } from "./shared.ts";
import { bindTrigger } from "./trigger.ts";

const ALLOWED = new Set(["_id", "_trigger", "_file"]);

export function bindFragmentRef(yaml: YamlValue, loc: Location): Result<FragmentRef> {
  if (!isPlainObject(yaml)) {
    return fail(error("BIND", `a _fragments entry must be a {_id, _trigger, _file} map`, loc));
  }
  const findings: Finding[] = [];

  if (typeof yaml._id !== "string") findings.push(error("BIND", `a _fragments entry requires a string "_id"`, loc));
  if (typeof yaml._file !== "string") findings.push(error("BIND", `a _fragments entry requires a string "_file"`, loc));
  for (const k of Object.keys(yaml)) {
    if (!ALLOWED.has(k)) findings.push(error("CLOSED_VOCAB", `unexpected key "${k}" in a _fragments entry (only _id, _trigger, _file)`, loc));
  }

  // _trigger is a single-key map { token: arg } — unwrap, then bind.
  let trigger: FragmentRef["trigger"] | undefined;
  const trig = yaml._trigger;
  if (!isPlainObject(trig)) {
    findings.push(error("BIND", `_trigger must be a single-key map (e.g. { _glob: ... })`, loc));
  } else {
    const tk = Object.keys(trig);
    if (tk.length !== 1) {
      findings.push(error("BIND", `_trigger must have exactly one key, got: ${tk.join(", ")}`, loc));
    } else {
      const r = bindTrigger(tk[0], trig[tk[0]], { ...loc, path: "_trigger" });
      if (r.ok) trigger = r.value;
      else findings.push(...r.findings);
    }
  }

  if (findings.length > 0 || trigger === undefined || typeof yaml._id !== "string" || typeof yaml._file !== "string") {
    if (findings.length === 0) findings.push(error("BIND", `_fragments entry could not be bound`, loc));
    return fail(...findings);
  }
  return ok({ id: yaml._id, trigger, file: yaml._file });
}
