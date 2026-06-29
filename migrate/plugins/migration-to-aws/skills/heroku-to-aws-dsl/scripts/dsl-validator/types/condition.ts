// scripts/dsl-validator/types/condition.ts
//
// Tier 2 entry type. Source: INTERPRETER.md §"_preconditions" (lines 79-93),
// §"_postconditions" (lines 279-289).
//
// ONE item in a `_preconditions` or `_postconditions` list. The grammar does NOT
// distinguish the item SHAPE between pre and post (only which list it sits in),
// so pre and post share this ONE type, tagged by `context`.
//
// This is the first Tier-2 type: it COMPOSES two Tier-1 atoms — a CheckVerb (the
// test) plus an optional ErrorAction (the failure response). Because it composes
// them, the Tier-1 guarantees hold here for free (e.g. a `_halt_and_inform`
// onFailure is structurally required to carry a message).
//
// Pure types only. Parser invariants (exactly-one-verb-key, _assert-post-only,
// missing-onFailure-on-non-assert) are enforced in the check layer, not here.

import { type CheckVerb } from "./check-verb.ts";
import { type ErrorAction } from "./error-action.ts";

/** Which list the item came from. Lets the "_assert is post-only" check fire. */
export type ConditionContext = "pre" | "post";

export interface Condition {
  /** The test — exactly one check verb (parser enforces "exactly one verb key"). */
  readonly verb: CheckVerb;
  /**
   * The failure response. Optional: only `_assert` has a documented default
   * (halt) when omitted; a check warns if a non-`_assert` verb has none.
   */
  readonly onFailure?: ErrorAction;
  readonly context: ConditionContext;
}
