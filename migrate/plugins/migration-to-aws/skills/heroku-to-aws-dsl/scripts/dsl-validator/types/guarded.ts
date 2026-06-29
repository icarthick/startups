// scripts/dsl-validator/types/guarded.ts
//
// Tier 2 entry type. Source: INTERPRETER.md §"_knowledge" (lines 100-114),
// §"_templates" (~145-155).
//
// ONE entry in a phase's `_knowledge` OR `_templates` list — a file reference
// plus an optional load guard. The phase _knowledge/_templates is the SOLE load
// decision (a file loads IFF its `_when` is true; a bare `file:` always loads).
// Composes the Tier-1 WhenCondition (the third `_when` context).
//
// ONE type for both lists: identical shape + loading contract; only the semantic
// `role` differs (knowledge = lookup data consumed; template = skeleton emitted).
//
// Pure types only. The central guard-scope check (`when` may reference only the
// phase _input), path resolution, single-load-owner, and role/path conventions
// all live in the check layer.

import { type WhenCondition } from "./when-condition.ts";

/** Which list the entry came from — drives path + semantic checks. */
export type GuardedRole = "knowledge" | "template";

export interface Guarded {
  /** The data/template file path (author-namespace key; value is structure-validated). */
  readonly file: string;
  /** Optional load guard. ABSENT = always loads. */
  readonly when?: WhenCondition;
  readonly role: GuardedRole;
}
