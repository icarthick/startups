// scripts/dsl-validator/binders/error-action.ts
//
// Leaf binder: YamlValue -> ErrorAction. The first binder — validates + constructs
// a Tier-1 atom, producing Findings (not throwing) on non-conformance.
//
// Two input shapes the grammar produces (confirmed against real frontmatter):
//   - bare token:      "_unrecoverable"                  -> nullary (no message)
//   - single-key map:  { _halt_and_inform: "<msg>" }     -> STOP variant + message
//
// Enforces the corrected Type-1 model: only the two STOP actions
// (_halt_and_inform, _unrecoverable) may carry a message; the three CONTINUE
// actions are nullary.

import {
  type ErrorAction,
  type ErrorActionKind,
  ERROR_ACTION_KINDS,
  isErrorActionKind,
} from "../types/error-action.ts";
import { type YamlValue } from "../parser/yaml.ts";
import { type Location, type Result, error, fail, ok } from "../findings.ts";

const STOP_KINDS: ReadonlySet<ErrorActionKind> = new Set(["_halt_and_inform", "_unrecoverable"]);

function isPlainObject(v: YamlValue): v is { readonly [k: string]: YamlValue } {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

export function bindErrorAction(yaml: YamlValue, loc: Location): Result<ErrorAction> {
  // --- bare token form: a string ---
  if (typeof yaml === "string") {
    if (!isErrorActionKind(yaml)) {
      return fail(error("CLOSED_VOCAB", `unknown error action "${yaml}" (expected one of ${ERROR_ACTION_KINDS.join(", ")})`, loc));
    }
    // bare = no message (legal for any action; STOP actions simply omit it here)
    return ok({ kind: yaml } as ErrorAction);
  }

  // --- single-key map form: { token: message } ---
  if (isPlainObject(yaml)) {
    const keys = Object.keys(yaml);
    if (keys.length !== 1) {
      return fail(error("BIND", `an error action must be a single key, got ${keys.length}: {${keys.join(", ")}}`, loc));
    }
    const token = keys[0];
    if (!isErrorActionKind(token)) {
      return fail(error("CLOSED_VOCAB", `unknown error action "${token}" (expected one of ${ERROR_ACTION_KINDS.join(", ")})`, loc));
    }
    const msgVal = yaml[token];
    if (!STOP_KINDS.has(token)) {
      // CONTINUE action carrying a message — invalid (those are nullary)
      return fail(error("BIND", `error action "${token}" is a CONTINUE action and carries no message`, loc));
    }
    if (typeof msgVal !== "string") {
      return fail(error("BIND", `error action "${token}" message must be a string`, loc));
    }
    return ok({ kind: token, message: msgVal } as ErrorAction);
  }

  return fail(error("BIND", `not a valid error action (expected a token or a single-key map)`, loc));
}
