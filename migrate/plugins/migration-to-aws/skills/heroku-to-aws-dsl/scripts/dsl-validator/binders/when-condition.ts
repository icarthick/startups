// scripts/dsl-validator/binders/when-condition.ts
//
// Leaf binder: YamlValue -> WhenCondition. A _when value is a plain-language
// string. Trivial, but its own binder so the 4 _when contexts (trigger,
// knowledge-guard, re-entry if, step gate) all bind through one place.

import { type WhenCondition } from "../types/when-condition.ts";
import { type YamlValue } from "../parser/yaml.ts";
import { type Location, type Result, error, fail, ok } from "../findings.ts";

export function bindWhenCondition(yaml: YamlValue, loc: Location): Result<WhenCondition> {
  if (typeof yaml !== "string") {
    return fail(error("BIND", `a _when condition must be a plain-language string`, loc));
  }
  if (yaml.trim() === "") {
    return fail(error("BIND", `a _when condition must not be empty`, loc));
  }
  return ok({ condition: yaml });
}
