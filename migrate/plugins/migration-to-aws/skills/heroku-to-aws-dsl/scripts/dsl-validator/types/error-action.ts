// scripts/dsl-validator/types/error-action.ts
//
// Tier 1 value type. Source: INTERPRETER.md §"ERROR ACTIONS", lines 349-368.
//
// The closed set of 5 error-handling actions. Modeled as a discriminated union
// on `kind`, where `kind` IS the raw DSL token (e.g. "_halt_and_inform") so the
// type mirrors the grammar literally and parsing needs no translation layer.
//
// Only the two STOP variants (`_halt_and_inform`, `_unrecoverable`) carry an
// OPTIONAL message — they SURFACE text on failure. Evidence: both appear with a
// block-scalar message in `_on_failure` carriers AND bare (`_on_failure:
// _unrecoverable` on asserts), so the message is OPTIONAL on each. The three
// CONTINUE variants are nullary (they never surface a message).

/** Control-flow effect of an action. */
export type Control = "STOP" | "CONTINUE";

/**
 * Phase-status transition an action triggers.
 * `null` = the spec is silent (treated as "unchanged"); recorded, not invented.
 */
export type StatusEffect = "retain_in_progress" | "revert_pending" | null;

export interface HaltAndInform {
  readonly kind: "_halt_and_inform";
  /** Optional. The message surfaced alongside the GATE_FAIL diagnostic. */
  readonly message?: string;
}
export interface WarnAndSkip {
  readonly kind: "_warn_and_skip";
}
export interface Defer {
  readonly kind: "_defer";
}
export interface DefaultAndWarn {
  readonly kind: "_default_and_warn";
}
export interface Unrecoverable {
  readonly kind: "_unrecoverable";
  /** Optional. The error message surfaced when the phase reverts to pending. */
  readonly message?: string;
}

/** The closed set of 5 error actions (INTERPRETER.md lines 355-364). */
export type ErrorAction =
  | HaltAndInform
  | WarnAndSkip
  | Defer
  | DefaultAndWarn
  | Unrecoverable;

/** The discriminant tokens, on their own. */
export type ErrorActionKind = ErrorAction["kind"];

/**
 * The closed-set source of truth: the parser validates tokens against this, and
 * the "closed vocabulary" (Golden rule 4) check reads it. One place, no drift.
 */
export const ERROR_ACTION_KINDS: readonly ErrorActionKind[] = [
  "_halt_and_inform",
  "_warn_and_skip",
  "_defer",
  "_default_and_warn",
  "_unrecoverable",
] as const;

/** Type guard: is a raw string one of the closed action tokens? */
export function isErrorActionKind(s: string): s is ErrorActionKind {
  return (ERROR_ACTION_KINDS as readonly string[]).includes(s);
}

/**
 * Static semantics per variant, transcribed from INTERPRETER.md lines 355-364.
 * Kept OFF the variant shapes (which stay pure) and in one lookup table that
 * checks consume — e.g. "a per-item loop failure must not use a STOP action".
 */
export const ERROR_ACTION_SEMANTICS: Record<
  ErrorActionKind,
  { readonly control: Control; readonly statusEffect: StatusEffect; readonly sideEffect: string }
> = {
  _halt_and_inform: {
    control: "STOP",
    statusEffect: "retain_in_progress",
    sideEffect: "surface message + GATE_FAIL diagnostic",
  },
  _warn_and_skip: {
    control: "CONTINUE",
    statusEffect: null,
    sideEffect: "append warning; skip the CURRENT item",
  },
  _defer: {
    control: "CONTINUE",
    statusEffect: null,
    sideEffect: "append an entry to the deferred[] accumulator",
  },
  _default_and_warn: {
    control: "CONTINUE",
    statusEffect: null,
    sideEffect: "apply the documented default value; append a warning",
  },
  _unrecoverable: {
    control: "STOP",
    statusEffect: "revert_pending",
    sideEffect: "surface the error; revert phase to pending, preserving prior phases",
  },
};
