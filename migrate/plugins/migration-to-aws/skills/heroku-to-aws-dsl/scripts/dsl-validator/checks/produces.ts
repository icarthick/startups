// scripts/dsl-validator/checks/produces.ts
//
// Cross-unit check: the ownership identity (INTERPRETER 222-224) —
//   phase._produces  ==  union( fragment._produces )  ∪  assembler._produces
//                         ∪  assembler._mutates
// Each artifact has exactly one creator; the phase's declared output must equal
// what its units actually create/mutate. Matched by basename.

import { type CrossUnitCheck, type LoadedUnit, indexUnits } from "./check.ts";
import { type Finding, error } from "../findings.ts";

const base = (p: string): string => p.split("/").pop() ?? p;

export const producesCheck: CrossUnitCheck = {
  code: "PRODUCES",
  run(units: readonly LoadedUnit[]): readonly Finding[] {
    const idx = indexUnits(units);
    const findings: Finding[] = [];

    for (const ph of idx.phases) {
      if (ph.unit.kind !== "phase") continue;
      const fm = ph.unit.frontmatter;
      const declared = fm.produces.map(base);
      const declaredFull = fm.produces; // keep dir prefixes like "terraform/"

      // Artifacts the phase's assembler READS are intermediates (fragment->assembler
      // handoffs, often _-prefixed) and are NOT phase outputs — exempt them.
      const intermediates = new Set<string>();
      for (const member of idx.byOwningPhase.get(fm.phase) ?? []) {
        if (member.unit.kind === "assembler") {
          (member.unit.frontmatter.reads ?? []).forEach((r) => intermediates.add(base(r)));
        }
      }

      // Coverage: a produced file is covered if its basename is declared, OR a
      // declared directory prefix ("terraform/") covers its path.
      const isCovered = (path: string): boolean =>
        declared.includes(base(path)) || declaredFull.includes(path) || declaredFull.some((d) => d.endsWith("/") && path.startsWith(d));

      const owned: string[] = [];
      for (const member of idx.byOwningPhase.get(fm.phase) ?? []) {
        if (member.unit.kind === "fragment") {
          member.unit.frontmatter.produces.forEach((p) => owned.push(p));
        } else if (member.unit.kind === "assembler") {
          member.unit.frontmatter.produces.forEach((p) => owned.push(p));
          (member.unit.frontmatter.mutates ?? []).forEach((p) => owned.push(p));
        }
      }

      // owned but neither declared nor an intermediate -> the phase omits a real output
      for (const o of owned) {
        if (intermediates.has(base(o))) continue; // assembler-consumed handoff
        if (!isCovered(o)) {
          findings.push(error("PRODUCES", `phase "${fm.phase}" units create/mutate "${o}" but the phase _produces does not list it (or a covering directory)`, { file: ph.file }));
        }
      }
      // declared (file, not dir) but nothing creates/mutates it -> dead output
      const ownedBases = new Set(owned.map(base));
      for (const d of declaredFull) {
        if (d.endsWith("/")) continue; // directory outputs are covered by member files
        if (!ownedBases.has(base(d))) {
          findings.push(error("PRODUCES", `phase "${fm.phase}" declares _produces "${d}" but no fragment/assembler creates or mutates it`, { file: ph.file }));
        }
      }
    }
    return findings;
  },
};
