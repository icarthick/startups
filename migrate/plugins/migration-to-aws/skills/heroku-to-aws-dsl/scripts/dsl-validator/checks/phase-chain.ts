// scripts/dsl-validator/checks/phase-chain.ts
//
// Cross-unit check: the phase chain is consistent. Every phase's _advances_to
// names a real phase (or the terminal "complete"); every _requires_phase names a
// real phase (or null for the first). Warns on a phase no one advances to (an
// orphan) except the first.

import { type CrossUnitCheck, type LoadedUnit, indexUnits } from "./check.ts";
import { type Finding, error, warning } from "../findings.ts";

const TERMINAL = new Set(["complete", "done", "end"]);

export const phaseChainCheck: CrossUnitCheck = {
  code: "FRAGMENT_REF",
  run(units: readonly LoadedUnit[]): readonly Finding[] {
    const idx = indexUnits(units);
    const findings: Finding[] = [];

    const names = new Set<string>();
    for (const ph of idx.phases) if (ph.unit.kind === "phase") names.add(ph.unit.frontmatter.phase);

    const advancedTo = new Set<string>();
    for (const ph of idx.phases) {
      if (ph.unit.kind !== "phase") continue;
      const fm = ph.unit.frontmatter;
      // _advances_to must be a known phase or terminal
      if (!names.has(fm.advancesTo) && !TERMINAL.has(fm.advancesTo)) {
        findings.push(error("FRAGMENT_REF", `phase "${fm.phase}" _advances_to "${fm.advancesTo}" is not a known phase (or terminal)`, { file: ph.file }));
      } else {
        advancedTo.add(fm.advancesTo);
      }
      // _requires_phase must be a known phase or null
      if (fm.requiresPhase !== null && !names.has(fm.requiresPhase)) {
        findings.push(error("FRAGMENT_REF", `phase "${fm.phase}" _requires_phase "${fm.requiresPhase}" is not a known phase`, { file: ph.file }));
      }
    }

    // a phase nobody advances to (and isn't the first/requires-null) is an orphan
    for (const ph of idx.phases) {
      if (ph.unit.kind !== "phase") continue;
      const fm = ph.unit.frontmatter;
      if (fm.requiresPhase !== null && !advancedTo.has(fm.phase)) {
        findings.push(warning("FRAGMENT_REF", `phase "${fm.phase}" is not the target of any _advances_to (unreachable in the chain)`, { file: ph.file }));
      }
    }
    return findings;
  },
};
