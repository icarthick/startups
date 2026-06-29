// scripts/dsl-validator/binders/shared.ts
//
// Small helpers shared across binders — kept in one place so no binder
// re-implements them (the single-source discipline).

import { type SourceExistsArg } from "../types/check-verb.ts";
import { type YamlValue } from "../parser/yaml.ts";
import { type Finding, type Location, type Result, error, fail, ok } from "../findings.ts";

/** Narrow a YamlValue to a plain map (not array, not null). */
export function isPlainObject(v: YamlValue): v is { readonly [k: string]: YamlValue } {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/** Coerce a scalar-or-list YAML value into a string[], or null if wrong-typed. */
export function asStrList(v: YamlValue): readonly string[] | null {
  if (typeof v === "string") return [v];
  if (Array.isArray(v) && v.every((x) => typeof x === "string")) return v as readonly string[];
  return null;
}

/**
 * Bind a `{glob, containing?}` argument — SHARED by `_check_source_exists` in both
 * the CheckVerb and Trigger binders (it is one shape in two grammars).
 */
export function bindSourceExistsArg(v: YamlValue, loc: Location): Result<SourceExistsArg> {
  if (!isPlainObject(v)) return fail(error("BIND", `_check_source_exists arg must be a {glob, containing?} map`, loc));
  if (typeof v.glob !== "string") return fail(error("BIND", `_check_source_exists requires a string "glob"`, loc));
  if (v.containing !== undefined && typeof v.containing !== "string") {
    return fail(error("BIND", `_check_source_exists "containing" must be a string`, loc));
  }
  return ok(v.containing === undefined ? { glob: v.glob } : { glob: v.glob, containing: v.containing });
}

/**
 * Bind a YAML array by mapping a per-item binder over it, COLLECTING all findings
 * (not stopping at the first bad item). Succeeds only if EVERY item bound.
 */
export function bindList<T>(
  v: YamlValue,
  itemBinder: (item: YamlValue, idx: number) => Result<T>,
  what: string,
  loc: Location,
): Result<readonly T[]> {
  if (!Array.isArray(v)) return fail(error("BIND", `${what} must be a list`, loc));
  const values: T[] = [];
  const findings: Finding[] = [];
  v.forEach((item, i) => {
    const r = itemBinder(item, i);
    if (r.ok) values.push(r.value);
    else findings.push(...r.findings);
  });
  if (findings.length > 0) return fail(...findings);
  return ok(values);
}
