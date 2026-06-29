// scripts/dsl-validator/types/assembler-ref.ts
//
// Tier 2 entry type. Source: INTERPRETER.md §"_assemble" (phase body). Resolves
// the Type-5 deferred sibling.
//
// In the PHASE frontmatter, `_assemble` is a REFERENCE to the single assembler
// file — shape `{_file}`. Distinct from the ASSEMBLER frontmatter's `_assemble`,
// which is the assembler's ID string (same key, two types by context). Simpler
// than FragmentRef: no `_id`, no `_trigger` — the assembler always runs, exactly
// one per phase.
//
// Pure types only. Checks (file resolves; the unit's _of_phase matches the owning
// phase) live in the check layer.

export interface AssemblerRef {
  /** `_file` — the assembler file path. */
  readonly file: string;
}
