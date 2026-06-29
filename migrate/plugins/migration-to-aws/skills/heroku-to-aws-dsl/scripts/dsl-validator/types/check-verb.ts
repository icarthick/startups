// scripts/dsl-validator/types/check-verb.ts
//
// Tier 1 value type. Source: INTERPRETER.md §"_preconditions" (lines 84-93),
// §"_postconditions" (lines 279-289).
//
// The closed set of CHECK verbs. A precondition/postcondition item is "one check
// verb + an _on_failure action"; this type is the verb half (the _on_failure half
// is ErrorAction, paired at the Tier-2 Precondition).
//
// Modeled as a discriminated union on `kind` (uniform with ErrorAction), where
// `kind` IS the raw DSL verb token. The verbs have HETEROGENEOUS argument shapes,
// so each variant carries its own argument type.

/** Where a verb may legally appear. */
export type CheckContext = "pre" | "post" | "both";

/**
 * `{glob, containing?}` argument. Defined HERE and SHARED with the trigger-form
 * type (`_check_source_exists` is both a check verb and a trigger form, same
 * shape — see dsl-types.md Type 2, parked nuance).
 */
export interface SourceExistsArg {
  readonly glob: string;
  readonly containing?: string;
}

export interface CheckPhaseCompleted {
  readonly kind: "_check_phase_completed";
  /** The phase whose status must be "completed". */
  readonly phase: string;
}
export interface CheckSingleActivePhase {
  readonly kind: "_check_single_active_phase";
  // nullary — the grammar's `: true` argument is vestigial and carries no info.
}
export interface CheckFileExists {
  readonly kind: "_check_file_exists";
  readonly paths: string | readonly string[];
}
export interface ValidateJson {
  readonly kind: "_validate_json";
  readonly paths: string | readonly string[];
}
export interface ValidateSchema {
  readonly kind: "_validate_schema";
  readonly file: string;
  /** Resolved relative to the skill's `schemas/` dir. */
  readonly schema: string;
}
export interface CheckSourceExists {
  readonly kind: "_check_source_exists";
  readonly arg: SourceExistsArg;
}
export interface Assert {
  readonly kind: "_assert";
  /** Plain-language condition that MUST hold. POST-ONLY. */
  readonly condition: string;
}

/** The closed set of 7 check verbs. */
export type CheckVerb =
  | CheckPhaseCompleted
  | CheckSingleActivePhase
  | CheckFileExists
  | ValidateJson
  | ValidateSchema
  | CheckSourceExists
  | Assert;

/** The discriminant tokens, on their own. */
export type CheckVerbKind = CheckVerb["kind"];

/**
 * Closed-set source of truth: the parser validates verb keys against this, and
 * the closed-vocabulary (Golden rule 4) check reads it. One place, no drift.
 */
export const CHECK_VERB_KINDS: readonly CheckVerbKind[] = [
  "_check_phase_completed",
  "_check_single_active_phase",
  "_check_file_exists",
  "_validate_json",
  "_validate_schema",
  "_check_source_exists",
  "_assert",
] as const;

/** Type guard: is a raw string one of the closed verb tokens? */
export function isCheckVerbKind(s: string): s is CheckVerbKind {
  return (CHECK_VERB_KINDS as readonly string[]).includes(s);
}

/**
 * Per-verb metadata: the context a verb may appear in, and (for `_assert`) the
 * implicit default action it performs on failure when no `_on_failure` is given
 * (INTERPRETER.md lines 281-283: emit `GATE_FAIL | reason=invalid` and halt).
 * Kept OFF the variant shapes; checks consume it (e.g. "`_assert` is post-only").
 */
export const CHECK_VERB_META: Record<
  CheckVerbKind,
  { readonly context: CheckContext; readonly defaultOnFailure?: "halt_gate_fail" }
> = {
  _check_phase_completed: { context: "both" },
  _check_single_active_phase: { context: "both" },
  _check_file_exists: { context: "both" },
  _validate_json: { context: "both" },
  _validate_schema: { context: "both" },
  _check_source_exists: { context: "both" },
  _assert: { context: "post", defaultOnFailure: "halt_gate_fail" },
};
