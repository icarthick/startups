// scripts/dsl-validator/checks/check.ts
//
// The check layer foundation. Checks consume typed Units (which the binders
// already validated for shape + closed-vocabulary) and produce Findings for the
// SEMANTIC / CROSS-REFERENCE rules the types and binders can't express.
//
// Two kinds:
//   - IntraUnitCheck: one Unit -> Findings  (regions, kind-match, USES, ...)
//   - CrossUnitCheck: all Units -> Findings (SUBSET, FRAGMENT_REF, PRODUCES, ...)

import { type Unit } from "../types/unit.ts";
import { type PhaseFrontmatter } from "../types/frontmatter.ts";
import { type Finding } from "../findings.ts";

/** A loaded unit paired with its file path (cross-unit checks need the path). */
export interface LoadedUnit {
  readonly file: string;
  readonly unit: Unit;
}

export interface IntraUnitCheck {
  readonly code: string; // dominant FindingCode this check emits (for catalog/filtering)
  readonly run: (loaded: LoadedUnit) => readonly Finding[];
}

export interface CrossUnitCheck {
  readonly code: string;
  readonly run: (units: readonly LoadedUnit[]) => readonly Finding[];
}

/** Run every intra-unit check over every unit, then every cross-unit check. */
export function runChecks(
  units: readonly LoadedUnit[],
  intra: readonly IntraUnitCheck[],
  cross: readonly CrossUnitCheck[],
): readonly Finding[] {
  const findings: Finding[] = [];
  for (const lu of units) {
    for (const c of intra) findings.push(...c.run(lu));
  }
  for (const c of cross) findings.push(...c.run(units));
  return findings;
}

// ---------------------------------------------------------------------------
// UnitIndex — links units together for cross-unit checks (phase <-> its fragments
// + assembler, by _of_phase / file path).
// ---------------------------------------------------------------------------

export interface UnitIndex {
  readonly all: readonly LoadedUnit[];
  readonly phases: readonly LoadedUnit[];
  /** units (fragment/assembler) keyed by their `_file`-relative path. */
  readonly byFile: ReadonlyMap<string, LoadedUnit>;
  /** fragment+assembler units grouped by their `_of_phase`. */
  readonly byOwningPhase: ReadonlyMap<string, readonly LoadedUnit[]>;
}

export function indexUnits(units: readonly LoadedUnit[]): UnitIndex {
  const phases = units.filter((u) => u.unit.kind === "phase");
  const byFile = new Map<string, LoadedUnit>();
  const byOwningPhase = new Map<string, LoadedUnit[]>();
  for (const lu of units) {
    byFile.set(lu.file, lu);
    if (lu.unit.kind === "fragment" || lu.unit.kind === "assembler") {
      const owner = lu.unit.frontmatter.ofPhase;
      const arr = byOwningPhase.get(owner) ?? [];
      arr.push(lu);
      byOwningPhase.set(owner, arr);
    }
  }
  return { all: units, phases, byFile, byOwningPhase };
}

/** The phase name a unit belongs to (phase -> its own name; frag/asm -> _of_phase). */
export function owningPhaseName(lu: LoadedUnit): string {
  return lu.unit.kind === "phase"
    ? (lu.unit.frontmatter as PhaseFrontmatter).phase
    : lu.unit.frontmatter.ofPhase;
}
