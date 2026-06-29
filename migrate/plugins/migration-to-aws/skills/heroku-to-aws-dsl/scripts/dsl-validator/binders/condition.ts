// scripts/dsl-validator/binders/condition.ts
//
// Tier-2 composite binder: a pre/postcondition item map -> Condition. The first
// MULTI-CHILD binder — it separates the single check-verb key from the sibling
// `_on_failure`, binds BOTH (bindCheckVerb + bindErrorAction), and MERGES their
// findings (collects all, not just the first). This is where the Result wrapper
// earns its keep.
//
// Item shape (from the grammar): a map with EXACTLY ONE check-verb key plus an
// OPTIONAL `_on_failure`. Any other key is invalid (closed-vocab).

import { type Condition, type ConditionContext } from "../types/condition.ts";
import { isCheckVerbKind } from "../types/check-verb.ts";
import { type YamlValue } from "../parser/yaml.ts";
import { type Finding, type Location, type Result, error, fail, ok } from "../findings.ts";
import { isPlainObject } from "./shared.ts";
import { bindCheckVerb } from "./check-verb.ts";
import { bindErrorAction } from "./error-action.ts";

const ON_FAILURE = "_on_failure";

export function bindCondition(yaml: YamlValue, context: ConditionContext, loc: Location): Result<Condition> {
  if (!isPlainObject(yaml)) {
    return fail(error("BIND", `a ${context}condition item must be a map (one check verb + optional _on_failure)`, loc));
  }

  const keys = Object.keys(yaml);
  const verbKeys = keys.filter((k) => isCheckVerbKind(k));
  const otherKeys = keys.filter((k) => !isCheckVerbKind(k) && k !== ON_FAILURE);

  const findings: Finding[] = [];

  // Exactly one verb key.
  if (verbKeys.length === 0) {
    findings.push(error("BIND", `condition item has no check verb (keys: ${keys.join(", ")})`, loc));
  } else if (verbKeys.length > 1) {
    findings.push(error("BIND", `condition item has more than one check verb: ${verbKeys.join(", ")}`, loc));
  }
  // No stray keys (closed vocabulary).
  for (const k of otherKeys) {
    findings.push(error("CLOSED_VOCAB", `unexpected key "${k}" in a condition item (only a check verb + _on_failure allowed)`, loc));
  }

  // Bind the verb (if we have exactly one) — collect its findings.
  let verb: Condition["verb"] | undefined;
  if (verbKeys.length === 1) {
    const token = verbKeys[0];
    const r = bindCheckVerb(token, yaml[token], loc);
    if (r.ok) verb = r.value;
    else findings.push(...r.findings);
  }

  // Bind the optional _on_failure — collect its findings.
  let onFailure: Condition["onFailure"] | undefined;
  if (ON_FAILURE in yaml) {
    const r = bindErrorAction(yaml[ON_FAILURE], { ...loc, path: ON_FAILURE });
    if (r.ok) onFailure = r.value;
    else findings.push(...r.findings);
  }

  if (findings.length > 0 || verb === undefined) {
    // ensure at least one finding if verb missing without an explicit error already
    if (findings.length === 0) findings.push(error("BIND", `condition item could not be bound`, loc));
    return fail(...findings);
  }

  return ok(onFailure === undefined ? { verb, context } : { verb, onFailure, context });
}
