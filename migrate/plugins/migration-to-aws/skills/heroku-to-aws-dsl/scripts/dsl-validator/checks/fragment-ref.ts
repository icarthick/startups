// scripts/dsl-validator/checks/fragment-ref.ts
//
// Cross-unit check: every phase's _fragments[] entry and its _assemble ref must
// RESOLVE — the referenced file exists, is the right kind, belongs to this phase
// (_of_phase), and (for fragments) its _fragment id matches the ref's _id.

import { type CrossUnitCheck, type LoadedUnit, indexUnits } from "./check.ts";
import { type Finding, error } from "../findings.ts";

export const fragmentRefCheck: CrossUnitCheck = {
  code: "FRAGMENT_REF",
  run(units: readonly LoadedUnit[]): readonly Finding[] {
    const idx = indexUnits(units);
    const findings: Finding[] = [];

    for (const ph of idx.phases) {
      if (ph.unit.kind !== "phase") continue;
      const fm = ph.unit.frontmatter;
      const phaseName = fm.phase;

      // each fragment ref
      for (const ref of fm.fragments) {
        const target = idx.byFile.get(ref.file);
        if (!target) {
          findings.push(error("FRAGMENT_REF", `_fragments _id="${ref.id}" _file="${ref.file}" does not resolve to a unit file`, { file: ph.file }));
          continue;
        }
        if (target.unit.kind !== "fragment") {
          findings.push(error("FRAGMENT_REF", `_fragments _id="${ref.id}" points at a ${target.unit.kind}, expected a fragment`, { file: ph.file }));
          continue;
        }
        if (target.unit.frontmatter.fragment !== ref.id) {
          findings.push(error("FRAGMENT_REF", `_fragments _id="${ref.id}" but the file's _fragment is "${target.unit.frontmatter.fragment}"`, { file: ph.file }));
        }
        if (target.unit.frontmatter.ofPhase !== phaseName) {
          findings.push(error("FRAGMENT_REF", `fragment "${ref.id}" _of_phase="${target.unit.frontmatter.ofPhase}" but is referenced by phase "${phaseName}"`, { file: ph.file }));
        }
      }

      // the assembler ref
      const asm = idx.byFile.get(fm.assemble.file);
      if (!asm) {
        findings.push(error("FRAGMENT_REF", `_assemble _file="${fm.assemble.file}" does not resolve to a unit file`, { file: ph.file }));
      } else if (asm.unit.kind !== "assembler") {
        findings.push(error("FRAGMENT_REF", `_assemble points at a ${asm.unit.kind}, expected an assembler`, { file: ph.file }));
      } else if (asm.unit.frontmatter.ofPhase !== phaseName) {
        findings.push(error("FRAGMENT_REF", `assembler _of_phase="${asm.unit.frontmatter.ofPhase}" but is referenced by phase "${phaseName}"`, { file: ph.file }));
      }
    }
    return findings;
  },
};
