// scripts/dsl-validator/types/unit.ts
//
// Tier 4 unit type (the apex). Source: INTERPRETER.md §"Unit file regions"
// (lines 395-425), Golden rule 6.
//
// A whole `.md` file — the top-level type a parser produces. Every unit is
// EXACTLY, in order: Frontmatter -> H1 -> optional Orientation -> zero-or-more
// Steps -> NOTHING else. THREE kinds, matching the three Frontmatter kinds; the
// unit's kind MUST equal its frontmatter's kind.
//
// A `Phase` transitively composes EVERY type in the system — the whole typed
// graph meets here. Pure types only. Region invariants (phase-has-no-steps,
// orientation position/count, no-trailing-prose, kind-match) live in the check
// layer.

import {
  type PhaseFrontmatter,
  type FragmentFrontmatter,
  type AssemblerFrontmatter,
} from "./frontmatter.ts";
import { type Orientation } from "./orientation.ts";
import { type Step } from "./step.ts";

/** The body regions shared by all three unit kinds. */
export interface UnitRegions {
  /** The H1 title — cosmetic; the interpreter assigns it no meaning. */
  readonly title?: string;
  /** The optional `## Orientation` section. */
  readonly orientation?: Orientation;
  /**
   * The `## Step:` sections, in order. A check enforces the kind-specific rule:
   * EMPTY for a phase; NON-EMPTY for a fragment/assembler.
   */
  readonly steps: readonly Step[];
}

export interface Phase extends UnitRegions {
  readonly kind: "phase";
  readonly frontmatter: PhaseFrontmatter;
}

export interface Fragment extends UnitRegions {
  readonly kind: "fragment";
  readonly frontmatter: FragmentFrontmatter;
}

export interface Assembler extends UnitRegions {
  readonly kind: "assembler";
  readonly frontmatter: AssemblerFrontmatter;
}

/** A whole parsed unit file — discriminated on `kind`. */
export type Unit = Phase | Fragment | Assembler;

export type UnitKind = Unit["kind"];
