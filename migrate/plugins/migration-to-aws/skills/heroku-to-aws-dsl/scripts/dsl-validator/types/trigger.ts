// scripts/dsl-validator/types/trigger.ts
//
// Tier 1 value type. Source: INTERPRETER.md §"_trigger" (lines 185-193).
//
// WHEN a fragment runs ("the phase owns triggering, not the fragment"). Exactly
// ONE of 5 forms. A false trigger SKIPS the fragment — its artifact(s) simply
// absent; the assembler accounts for absence.
//
// Discriminated union on `kind` (uniform with ErrorAction/CheckVerb), where
// `kind` IS the raw DSL trigger token.

import { type SourceExistsArg } from "./check-verb.ts";
import { type WhenCondition } from "./when-condition.ts";

export interface AlwaysTrigger {
  readonly kind: "_always";
  // nullary — the grammar's `: true` is vestigial (consistent with _check_single_active_phase).
}
export interface GlobTrigger {
  readonly kind: "_glob";
  /** Workspace SOURCE file glob(s) — fires if a matching file exists. */
  readonly patterns: string | readonly string[];
}
export interface ArtifactExistsTrigger {
  readonly kind: "_artifact_exists";
  /** RUN artifact name(s) in $MIGRATION_DIR/ — fires if present. */
  readonly names: string | readonly string[];
}
export interface CheckSourceExistsTrigger {
  readonly kind: "_check_source_exists";
  /** Same `{glob, containing?}` shape as the CheckVerb of the same name (shared arg). */
  readonly arg: SourceExistsArg;
}
export interface WhenTrigger {
  readonly kind: "_when";
  /** Plain-language condition on phase inputs/preferences (a VALUE, not file presence). */
  readonly when: WhenCondition;
}

/** The closed set of 5 trigger forms. */
export type Trigger =
  | AlwaysTrigger
  | GlobTrigger
  | ArtifactExistsTrigger
  | CheckSourceExistsTrigger
  | WhenTrigger;

/** The discriminant tokens, on their own. */
export type TriggerKind = Trigger["kind"];

/**
 * Closed-set source of truth: the parser validates trigger keys against this,
 * and the closed-vocabulary (Golden rule 4) check reads it. One place, no drift.
 */
export const TRIGGER_KINDS: readonly TriggerKind[] = [
  "_always",
  "_glob",
  "_artifact_exists",
  "_check_source_exists",
  "_when",
] as const;

/** Type guard: is a raw string one of the closed trigger tokens? */
export function isTriggerKind(s: string): s is TriggerKind {
  return (TRIGGER_KINDS as readonly string[]).includes(s);
}

/**
 * Per-form metadata: what the form tests against. Kept OFF the variant shapes;
 * checks consume it (e.g. "_artifact_exists names should match some _produces").
 * `target` distinguishes the two glob-ish/list-ish forms that share arg shape.
 */
export const TRIGGER_META: Record<
  TriggerKind,
  { readonly target: "none" | "workspace_source" | "run_artifact" | "input_value" }
> = {
  _always: { target: "none" },
  _glob: { target: "workspace_source" },
  _artifact_exists: { target: "run_artifact" },
  _check_source_exists: { target: "workspace_source" },
  _when: { target: "input_value" },
};
