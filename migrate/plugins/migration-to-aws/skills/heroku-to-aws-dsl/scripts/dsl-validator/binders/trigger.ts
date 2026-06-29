// scripts/dsl-validator/binders/trigger.ts
//
// Leaf binder: (trigger token, arg YamlValue) -> Trigger. The 5-variant union.
// A _trigger value is a single-key map (e.g. { _check_source_exists: {...} }); the
// caller (bindFragmentRef) separates the token from its arg and passes them here.
//
// Arg shapes (from the grammar):
//   _always:              true                    (vestigial -> nullary)
//   _glob:                <pattern> | [patterns]  (string | string[])
//   _artifact_exists:     <name> | [names]        (string | string[])
//   _check_source_exists: {glob, containing?}      (map; SHARED shape w/ CheckVerb)
//   _when:                <plain-language>         (string -> WhenCondition)

import { type Trigger, isTriggerKind, TRIGGER_KINDS } from "../types/trigger.ts";
import { type YamlValue } from "../parser/yaml.ts";
import { type Location, type Result, error, fail, ok } from "../findings.ts";
import { bindWhenCondition } from "./when-condition.ts";
import { asStrList, bindSourceExistsArg } from "./shared.ts";

export function bindTrigger(token: string, arg: YamlValue, loc: Location): Result<Trigger> {
  if (!isTriggerKind(token)) {
    return fail(error("CLOSED_VOCAB", `unknown trigger "${token}" (expected one of ${TRIGGER_KINDS.join(", ")})`, loc));
  }
  switch (token) {
    case "_always": {
      // arg is the vestigial `true`; ignored (nullary).
      return ok({ kind: "_always" });
    }
    case "_glob": {
      const patterns = asStrList(arg);
      if (!patterns) return fail(error("BIND", `_glob requires a pattern or a list of patterns`, loc));
      return ok({ kind: "_glob", patterns });
    }
    case "_artifact_exists": {
      const names = asStrList(arg);
      if (!names) return fail(error("BIND", `_artifact_exists requires a name or a list of names`, loc));
      return ok({ kind: "_artifact_exists", names });
    }
    case "_check_source_exists": {
      const r = bindSourceExistsArg(arg, loc);
      if (!r.ok) return r;
      return ok({ kind: "_check_source_exists", arg: r.value });
    }
    case "_when": {
      const r = bindWhenCondition(arg, loc);
      if (!r.ok) return r;
      return ok({ kind: "_when", when: r.value });
    }
  }
}
