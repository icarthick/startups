// scripts/dsl-validator/types/when-condition.ts
//
// Tier 1 value type. Source: INTERPRETER.md §"_trigger" (line 188),
// §step-level `_when` (line 277), §"_knowledge" guard (`{file, _when}`).
//
// `_when` appears in THREE contexts — a fragment trigger, a step-level gate, and
// a _knowledge load guard. All three are structurally a plain-language condition,
// so they SHARE this one atom. What differs is the SCOPE the condition may
// reference (e.g. a knowledge guard may reference ONLY the phase _input) — that
// is a CHECK (guard-scope), not a shape difference.

export interface WhenCondition {
  /** The plain-language condition string, evaluated by the LLM at runtime. */
  readonly condition: string;
}
