// scripts/dsl-validator/types/re-entry-guard.ts
//
// Tier 2 entry type. Source: INTERPRETER.md §"_re_entry_guard" (lines 297-337).
//
// A top-level phase key (a SINGLE object, not a list entry) — a fail-closed
// interlock evaluated before _preconditions. Stops a phase re-run from silently
// invalidating downstream work. Composes Tier-1 ErrorAction; reuses WhenCondition
// for `if`.
//
// Resolves the parked `reason` nuance: `reason` (no underscore) is a plain-string
// DIAGNOSTIC field (populates the diagnostic `reason=`), distinct from
// ErrorAction's `message` and from the step-prose `_reason`.
//
// Pure types only. Checks (action must be STOP; `if` guard-scope = downstream/
// status; onConfirm matches the phase chain) live in the check layer.

import { type ErrorAction } from "./error-action.ts";
import { type WhenCondition } from "./when-condition.ts";

export interface ReEntryGuard {
  /** `if` — true when a downstream artifact exists / a later phase completed. */
  readonly if: WhenCondition;
  /** `action` — performed when `if` is true; normally _halt_and_inform (a STOP action). */
  readonly action: ErrorAction;
  /** `reason` — surfaced with the action; maps to the diagnostic `reason=` field. */
  readonly reason: string;
  /**
   * `on_confirm` — the reset performed ONLY on explicit user confirmation: a
   * named reset OR an inline downstream-artifact list. ABSENT = canonical cascade
   * from the phase chain. [SPEC-FUZZY — see dsl-types.md Type 7.]
   */
  readonly onConfirm?: string | readonly string[];
}
