// scripts/dsl-validator/binders/assembler-ref.ts
//
// Tier-2 binder: a phase's _assemble -> AssemblerRef. Shape `{_file}`.

import { type AssemblerRef } from "../types/assembler-ref.ts";
import { type YamlValue } from "../parser/yaml.ts";
import { type Finding, type Location, type Result, error, fail, ok } from "../findings.ts";
import { isPlainObject } from "./shared.ts";

const ALLOWED = new Set(["_file"]);

export function bindAssemblerRef(yaml: YamlValue, loc: Location): Result<AssemblerRef> {
  if (!isPlainObject(yaml)) {
    return fail(error("BIND", `_assemble must be a { _file } map`, loc));
  }
  const findings: Finding[] = [];
  if (typeof yaml._file !== "string") findings.push(error("BIND", `_assemble requires a string "_file"`, loc));
  for (const k of Object.keys(yaml)) {
    if (!ALLOWED.has(k)) findings.push(error("CLOSED_VOCAB", `unexpected key "${k}" in _assemble (only _file)`, loc));
  }
  if (findings.length > 0 || typeof yaml._file !== "string") {
    if (findings.length === 0) findings.push(error("BIND", `_assemble could not be bound`, loc));
    return fail(...findings);
  }
  return ok({ file: yaml._file });
}
