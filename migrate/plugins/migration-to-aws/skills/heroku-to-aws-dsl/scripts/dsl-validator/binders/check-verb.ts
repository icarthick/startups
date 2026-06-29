// scripts/dsl-validator/binders/check-verb.ts
//
// Leaf binder: (verb token, arg YamlValue) -> CheckVerb. The 7-variant union,
// each with its OWN argument shape. The caller (bindCondition) separates the verb
// key from the sibling _on_failure and passes the verb token + its arg here.
//
// Arg shapes (from the grammar):
//   _check_phase_completed:     <phase name>            (string)
//   _check_single_active_phase: true                    (vestigial -> nullary)
//   _check_file_exists:         <path> | [paths]        (string | string[])
//   _validate_json:             <path> | [paths]        (string | string[])
//   _validate_schema:           {file, schema}          (map)
//   _check_source_exists:       {glob, containing?}      (map)
//   _assert:                    <plain-language>         (string)

import {
  type CheckVerb,
  isCheckVerbKind,
  CHECK_VERB_KINDS,
} from "../types/check-verb.ts";
import { type YamlValue } from "../parser/yaml.ts";
import { type Location, type Result, error, fail, ok } from "../findings.ts";
import { asStrList, bindSourceExistsArg, isPlainObject } from "./shared.ts";

export function bindCheckVerb(token: string, arg: YamlValue, loc: Location): Result<CheckVerb> {
  if (!isCheckVerbKind(token)) {
    return fail(error("CLOSED_VOCAB", `unknown check verb "${token}" (expected one of ${CHECK_VERB_KINDS.join(", ")})`, loc));
  }

  switch (token) {
    case "_check_phase_completed": {
      if (typeof arg !== "string") return fail(error("BIND", `_check_phase_completed requires a phase name (string)`, loc));
      return ok({ kind: "_check_phase_completed", phase: arg });
    }
    case "_check_single_active_phase": {
      // arg is the vestigial `true`; ignored (nullary variant).
      return ok({ kind: "_check_single_active_phase" });
    }
    case "_check_file_exists": {
      const paths = asStrList(arg);
      if (!paths) return fail(error("BIND", `_check_file_exists requires a path or a list of paths`, loc));
      return ok({ kind: "_check_file_exists", paths });
    }
    case "_validate_json": {
      const paths = asStrList(arg);
      if (!paths) return fail(error("BIND", `_validate_json requires a path or a list of paths`, loc));
      return ok({ kind: "_validate_json", paths });
    }
    case "_validate_schema": {
      if (!isPlainObject(arg)) return fail(error("BIND", `_validate_schema requires a {file, schema} map`, loc));
      if (typeof arg.file !== "string" || typeof arg.schema !== "string") {
        return fail(error("BIND", `_validate_schema requires string "file" and "schema"`, loc));
      }
      return ok({ kind: "_validate_schema", file: arg.file, schema: arg.schema });
    }
    case "_check_source_exists": {
      const r = bindSourceExistsArg(arg, loc);
      if (!r.ok) return r;
      return ok({ kind: "_check_source_exists", arg: r.value });
    }
    case "_assert": {
      if (typeof arg !== "string") return fail(error("BIND", `_assert requires a plain-language condition (string)`, loc));
      return ok({ kind: "_assert", condition: arg });
    }
  }
}
