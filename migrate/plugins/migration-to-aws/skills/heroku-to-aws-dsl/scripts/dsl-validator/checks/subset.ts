// scripts/dsl-validator/checks/subset.ts
//
// Cross-unit check: SUBSET (single-load-owner). Every file a step's meta
// _knowledge/_templates names must be declared in the OWNING PHASE's _knowledge/
// _templates (the phase is the sole load decision; a step only USES). Links a
// fragment/assembler to its phase via _of_phase. Matched by basename.

import { type CrossUnitCheck, type LoadedUnit, indexUnits } from "./check.ts";
import { type Finding, error } from "../findings.ts";

const base = (p: string): string => p.split("/").pop() ?? p;

export const subsetCheck: CrossUnitCheck = {
  code: "SUBSET",
  run(units: readonly LoadedUnit[]): readonly Finding[] {
    const idx = indexUnits(units);
    const findings: Finding[] = [];

    // phase name -> the set of declared knowledge+template basenames
    const phaseDeclared = new Map<string, Set<string>>();
    for (const ph of idx.phases) {
      if (ph.unit.kind !== "phase") continue;
      const fm = ph.unit.frontmatter;
      const set = new Set<string>([
        ...(fm.knowledge ?? []).map((g) => base(g.file)),
        ...(fm.templates ?? []).map((g) => base(g.file)),
      ]);
      phaseDeclared.set(fm.phase, set);
    }

    for (const lu of units) {
      if (lu.unit.kind === "phase") continue;
      const phaseName = lu.unit.frontmatter.ofPhase;
      const declared = phaseDeclared.get(phaseName);
      if (!declared) continue; // a missing phase is a FRAGMENT_REF concern, not SUBSET
      for (const step of lu.unit.steps) {
        const used = [...(step.meta?.knowledge ?? []), ...(step.meta?.templates ?? [])];
        for (const file of used) {
          if (!declared.has(base(file))) {
            findings.push(
              error(
                "SUBSET",
                `step "${step.id}" uses "${file}" but phase "${phaseName}" does not declare it in _knowledge/_templates (single-load-owner)`,
                { file: lu.file, path: `Step:${step.id}` },
              ),
            );
          }
        }
      }
    }
    return findings;
  },
};
