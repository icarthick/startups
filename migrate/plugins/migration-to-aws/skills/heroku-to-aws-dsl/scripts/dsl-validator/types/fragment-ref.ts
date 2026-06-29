// scripts/dsl-validator/types/fragment-ref.ts
//
// Tier 2 entry type. Source: INTERPRETER.md §"_fragments" (lines 181-195).
//
// ONE entry in a phase's ordered `_fragments` list — the phase's reference to a
// fragment it composes ("the phase owns triggering, not the fragment"). Composes
// the Tier-1 Trigger union.
//
// Pure types only. Cross-reference checks (id <-> target file's _fragment, file
// resolves on disk, _id uniqueness within a phase) live in the check layer.
// Ordering is owned by the phase's FragmentRef[] array, not this entry. The
// `_file` load-timing ("load only when trigger true") is interpreter behavior,
// not shape.

import { type Trigger } from "./trigger.ts";

export interface FragmentRef {
  /** `_id` — fragment name; matches the target file's `_fragment` (cross-ref check). */
  readonly id: string;
  /** `_trigger` — WHEN this fragment runs. */
  readonly trigger: Trigger;
  /** `_file` — the fragment file path. */
  readonly file: string;
}
