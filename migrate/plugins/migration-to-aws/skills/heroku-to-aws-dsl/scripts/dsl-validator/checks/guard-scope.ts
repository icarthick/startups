// scripts/dsl-validator/checks/guard-scope.ts
//
// Cross-unit check (warning): a phase _knowledge/_templates _when guard may
// reference ONLY the phase's _input (evaluable when guards run). A guard that
// names a KNOWN downstream/produced artifact (something some phase _produces but
// this phase does not take as _input) is out-of-scope — the LLM can't evaluate it
// before that artifact exists.
//
// Heuristic (the _when is plain language), so findings are WARNINGS: we look for
// any *.json-like token in the guard that is a known produced artifact and not in
// this phase's _input.

import { type CrossUnitCheck, type LoadedUnit, indexUnits } from "./check.ts";
import { type Finding, warning } from "../findings.ts";

const FILE_TOKEN_RE = /\b([a-z0-9][a-z0-9._-]*\.json)\b/gi;
const base = (p: string): string => p.split("/").pop() ?? p;

export const guardScopeCheck: CrossUnitCheck = {
  code: "GUARD_SCOPE",
  run(units: readonly LoadedUnit[]): readonly Finding[] {
    const idx = indexUnits(units);
    const findings: Finding[] = [];

    // all artifacts any phase produces (basename set)
    const produced = new Set<string>();
    for (const ph of idx.phases) {
      if (ph.unit.kind !== "phase") continue;
      ph.unit.frontmatter.produces.forEach((p) => produced.add(base(p)));
    }

    for (const ph of idx.phases) {
      if (ph.unit.kind !== "phase") continue;
      const fm = ph.unit.frontmatter;
      const inInput = new Set(fm.input.map(base));
      const guards = [...(fm.knowledge ?? []), ...(fm.templates ?? [])].filter((g) => g.when);
      for (const g of guards) {
        const cond = g.when!.condition;
        for (const m of cond.matchAll(FILE_TOKEN_RE)) {
          const tok = base(m[1]);
          if (produced.has(tok) && !inInput.has(tok)) {
            findings.push(
              warning(
                "GUARD_SCOPE",
                `_when guard for "${g.file}" references produced artifact "${tok}" which is not in this phase's _input — guards may reference only _input`,
                { file: ph.file },
              ),
            );
          }
        }
      }
    }
    return findings;
  },
};
