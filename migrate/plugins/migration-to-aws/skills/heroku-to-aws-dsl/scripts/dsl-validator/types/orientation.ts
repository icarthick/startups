// scripts/dsl-validator/types/orientation.ts
//
// Tier 3 sub-document type. Source: INTERPRETER.md §"Unit file regions"
// (lines 401-414), Golden rule 6.
//
// The single optional `## Orientation` section, immediately after the H1.
// NON-NORMATIVE: the interpreter READS it for context but MUST NOT execute it; it
// carries NO binding instruction (every rule lives in the frontmatter or a
// `## Step:`). A unit MAY omit it; if present, exactly one, only here.
//
// Carried as its own type (not a bare string on the unit) so the
// "recap-with-pointer only" check has a clear home and `orientation?: Orientation`
// reads self-documenting.
//
// Pure types only. Checks (recap-with-pointer only / no rule-as-source prose;
// at most one, positioned after the H1) live in the check layer.

export interface Orientation {
  /** The non-normative orienting text, verbatim. */
  readonly prose: string;
}
