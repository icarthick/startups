// scripts/dsl-validator/types/meta.ts
//
// Tier 3 sub-document type. Source: INTERPRETER.md §"_steps" (lines 228-250),
// CORRECTED against the real meta-block vocabulary observed across all phases
// (see dsl-types.md Type 8 SPEC-GAP: the prose under-lists _templates/_reads/
// _mutates and over-lists _cases).
//
// The fenced ```meta``` block under a `## Step: <id>` heading — the step's
// machine contract. In FORM 2b, `_id` is the heading and `_reason` IS the prose
// body, so neither is here; `Meta` covers only the machine-contract keys.
//
// FLAT (no recursion): in 2b there is NO `_cases` key — `_branch_on` names the
// discriminant field and the CASE BODIES ARE PROSE. All fields optional (a step
// may have an empty meta block — pure-prose step).
//
// `_knowledge`/`_templates` here are uses-annotations (string[], NEVER load) —
// distinct from the phase-level Guarded[] of the same key name.
//
// Pure types only. Checks (uses-subset, FORM-1-leak rejection, reads/mutates
// only-on-assembler, writesVar cross-ref) live in the check layer.

import { type WhenCondition } from "./when-condition.ts";

export interface Meta {
  // --- uses-annotations (string[], NOT Guarded — never load) ---
  /** `_knowledge` — DATA files THIS step uses (must be a subset of the phase's). */
  readonly knowledge?: readonly string[];
  /** `_templates` — template files THIS step uses (parallels `_knowledge`). */
  readonly templates?: readonly string[];

  // --- iteration / branching ---
  /** `_for_each` — collection to iterate, in input order. */
  readonly forEach?: string;
  /** `_branch_on` — discriminant field; the case bodies are PROSE (no `_cases` in 2b). */
  readonly branchOn?: string;
  /** `_collect` — accumulator lists appended across the iteration. */
  readonly collect?: readonly string[];

  // --- outputs ---
  /** `_writes` — artifact written to $MIGRATION_DIR/. */
  readonly writes?: string;
  /** `_writes_var` — in-run STATE later steps reference (not a file). */
  readonly writesVar?: string;

  // --- assembler-step IO (assembler-unit steps only — a check enforces) ---
  /** `_reads` — files this step reads. */
  readonly reads?: readonly string[];
  /** `_mutates` — files this step mutates in place. */
  readonly mutates?: readonly string[];

  // --- gate ---
  /** `_when` — run this step ONLY if true (the fourth `_when` context). */
  readonly when?: WhenCondition;
}

/**
 * The closed set of FORM-2b meta-block keys (the DSL `_`-tokens, not the camelCase
 * field names). The parser validates meta-block keys against this; a key NOT here
 * (e.g. the FORM-1-only `_cases`/`_default`/`_steps`) in a 2b block = INVALID.
 */
export const META_KEYS: readonly string[] = [
  "_knowledge",
  "_templates",
  "_for_each",
  "_branch_on",
  "_collect",
  "_writes",
  "_writes_var",
  "_reads",
  "_mutates",
  "_when",
] as const;

/** FORM-1-only keys that must NOT appear in a FORM-2b meta block. */
export const FORM1_ONLY_META_KEYS: readonly string[] = ["_cases", "_default", "_steps"] as const;

/** Type guard: is a raw string a valid FORM-2b meta-block key? */
export function isMetaKey(s: string): boolean {
  return META_KEYS.includes(s);
}
