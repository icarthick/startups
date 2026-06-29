// scripts/dsl-validator/types/frontmatter.ts
//
// Tier 3 sub-document type. Source: INTERPRETER.md §"Phase identity" (31-38),
// §"_input" (44-57), §"_init" (59+), §"_fragments"/"_assemble" (167-236),
// §"_produces"/"_advances_to"/"_forbids_files" (339-345).
//
// The `---`...`---` STRUCTURAL contract block — "the single source of truth for
// the unit's contract." THREE distinct key-sets (phase = composer; fragment =
// unit of work; assembler = combine/enrich, terminal), so THREE types. Fragment
// and Assembler share UnitFrontmatterCore.
//
// Pure types only. Cross-unit checks (produces-ownership identity, _of_phase
// match, _init-iff-first-phase, reads/mutates-only-on-assembler, closed-vocab)
// live in the check layer.

import { type Condition } from "./condition.ts";
import { type Guarded } from "./guarded.ts";
import { type FragmentRef } from "./fragment-ref.ts";
import { type AssemblerRef } from "./assembler-ref.ts";
import { type ReEntryGuard } from "./re-entry-guard.ts";
import { type OnErrorTable } from "./on-error-table.ts";

/**
 * `_init` — a FIRST-phase-only setup block with its own verb sub-grammar
 * (`_init_migration_run`, etc.). Modeled SHALLOWLY for now (raw verb keys) — a
 * candidate for full verb-union modeling later, like CheckVerb. [SPEC: shallow.]
 */
export interface InitBlock {
  readonly verbs: Readonly<Record<string, unknown>>;
}

/** Shared by Fragment and Assembler frontmatter. */
export interface UnitFrontmatterCore {
  /** `_of_phase` — owning-phase back-reference. */
  readonly ofPhase: string;
  /** `_scope` — hard boundary. */
  readonly scope: string;
  /** `_produces` — files this unit CREATES. */
  readonly produces: readonly string[];
  /** `_preconditions` — optional unit-local checks. */
  readonly preconditions?: readonly Condition[];
  /** `_postconditions` — checks on the file(s) this unit wrote. */
  readonly postconditions: readonly Condition[];
  /** `_on_error` — the documentation table. */
  readonly onError: OnErrorTable;
}

export interface FragmentFrontmatter extends UnitFrontmatterCore {
  readonly kind: "fragment";
  /** `_fragment` — id; matches the phase's `_fragments[]._id`. */
  readonly fragment: string;
}

export interface AssemblerFrontmatter extends UnitFrontmatterCore {
  readonly kind: "assembler";
  /** `_assemble` — id (the assembler's OWN id string, not a ref). */
  readonly assemble: string;
  /** `_reads` — fragment artifacts it consumes (0..N). */
  readonly reads?: readonly string[];
  /** `_mutates` — fragment artifacts it edits in place (0..N; the only mutator). */
  readonly mutates?: readonly string[];
}

export interface PhaseFrontmatter {
  readonly kind: "phase";
  /** `_phase` — identity, used in all diagnostics. */
  readonly phase: string;
  /** `_title` — cosmetic. */
  readonly title?: string;
  /** `_requires_phase` — upstream gate; `null` = first phase. */
  readonly requiresPhase: string | null;
  /** `_scope` — hard boundary. */
  readonly scope: string;
  /** `_init` — FIRST phase only (present iff `requiresPhase == null`). */
  readonly init?: InitBlock;
  /** `_re_entry_guard` — the re-run interlock. */
  readonly reEntryGuard?: ReEntryGuard;
  /** `_input` — artifact filenames / workspace globs consumed. */
  readonly input: readonly string[];
  /** `_preconditions` — checks run before steps. */
  readonly preconditions?: readonly Condition[];
  /** `_knowledge` — the SOLE load decision (guarded data files). */
  readonly knowledge?: readonly Guarded[];
  /** `_templates` — guarded output-skeleton files. */
  readonly templates?: readonly Guarded[];
  /** `_fragments` — the ordered composition. */
  readonly fragments: readonly FragmentRef[];
  /** `_assemble` — reference to the single assembler file. */
  readonly assemble: AssemblerRef;
  /** `_postconditions` — cross-cutting checks. */
  readonly postconditions?: readonly Condition[];
  /** `_produces` — the phase's artifacts. */
  readonly produces: readonly string[];
  /** `_advances_to` — the next phase. */
  readonly advancesTo: string;
  /** `_forbids_files` — patterns that must NOT be created. */
  readonly forbidsFiles?: readonly string[];
  /** `_on_error` — the documentation table. */
  readonly onError: OnErrorTable;
}

/** Any unit's frontmatter — discriminated on `kind`. */
export type Frontmatter = PhaseFrontmatter | FragmentFrontmatter | AssemblerFrontmatter;

export type FrontmatterKind = Frontmatter["kind"];
