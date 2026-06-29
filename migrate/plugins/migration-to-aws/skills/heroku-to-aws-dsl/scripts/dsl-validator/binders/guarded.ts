// scripts/dsl-validator/binders/guarded.ts
//
// Tier-2 binder: a _knowledge/_templates entry -> Guarded. Shape `{file, _when?}`.
// The `role` (knowledge|template) is supplied by the caller (the frontmatter
// binder knows which list it is parsing).

import { type Guarded, type GuardedRole } from "../types/guarded.ts";
import { type YamlValue } from "../parser/yaml.ts";
import { type Finding, type Location, type Result, error, fail, ok } from "../findings.ts";
import { isPlainObject } from "./shared.ts";
import { bindWhenCondition } from "./when-condition.ts";

const ALLOWED = new Set(["file", "_when"]);

export function bindGuarded(yaml: YamlValue, role: GuardedRole, loc: Location): Result<Guarded> {
  if (!isPlainObject(yaml)) {
    return fail(error("BIND", `a _${role === "template" ? "templates" : "knowledge"} entry must be a {file, _when?} map`, loc));
  }
  const findings: Finding[] = [];

  if (typeof yaml.file !== "string") {
    findings.push(error("BIND", `a ${role} entry requires a string "file"`, loc));
  }
  for (const k of Object.keys(yaml)) {
    if (!ALLOWED.has(k)) findings.push(error("CLOSED_VOCAB", `unexpected key "${k}" in a ${role} entry (only file, _when)`, loc));
  }

  let when: Guarded["when"] | undefined;
  if ("_when" in yaml) {
    const r = bindWhenCondition(yaml._when, { ...loc, path: "_when" });
    if (r.ok) when = r.value;
    else findings.push(...r.findings);
  }

  if (findings.length > 0 || typeof yaml.file !== "string") {
    if (findings.length === 0) findings.push(error("BIND", `${role} entry could not be bound`, loc));
    return fail(...findings);
  }
  return ok(when === undefined ? { file: yaml.file, role } : { file: yaml.file, when, role });
}
