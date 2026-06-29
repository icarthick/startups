// scripts/dsl-validator/binders/on-error-table.ts
//
// Tier-2 binder: an _on_error block -> OnErrorTable. A map of error-action names
// to their {effect, status} documentation. NOT executed — documentation only.

import { type OnErrorTable, type OnErrorTableEntry } from "../types/on-error-table.ts";
import { type ErrorActionKind, isErrorActionKind } from "../types/error-action.ts";
import { type YamlValue } from "../parser/yaml.ts";
import { type Finding, type Location, type Result, error, fail, ok } from "../findings.ts";
import { isPlainObject } from "./shared.ts";

export function bindOnErrorTable(yaml: YamlValue, loc: Location): Result<OnErrorTable> {
  if (!isPlainObject(yaml)) {
    return fail(error("BIND", `_on_error must be a map of action -> {effect, status}`, loc));
  }
  const findings: Finding[] = [];
  const entries: Partial<Record<ErrorActionKind, OnErrorTableEntry>> = {};

  for (const [k, v] of Object.entries(yaml)) {
    if (!isErrorActionKind(k)) {
      findings.push(error("CLOSED_VOCAB", `unknown error action "${k}" in _on_error table`, loc));
      continue;
    }
    if (!isPlainObject(v) || typeof v.effect !== "string" || typeof v.status !== "string") {
      findings.push(error("BIND", `_on_error["${k}"] must be a {effect, status} map of strings`, loc));
      continue;
    }
    entries[k] = { effect: v.effect, status: v.status };
  }

  if (findings.length > 0) return fail(...findings);
  return ok({ entries });
}
