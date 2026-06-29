// scripts/dsl-validator/checks/uses.ts
//
// Intra-unit check: USES binding. Every [_uses: F] marker a step's prose carries
// MUST name a file declared in that step's meta _knowledge/_templates. The
// structured Step.uses projection makes this a clean set check (no regex here —
// extraction already happened in bindStep).
//
// Matching is by BASENAME (prose tags "dyno-fargate-sizing.json"; meta lists
// "knowledge/design/dyno-fargate-sizing.json").

import { type IntraUnitCheck, type LoadedUnit } from "./check.ts";
import { type Finding, error } from "../findings.ts";

const base = (p: string): string => p.split("/").pop() ?? p;

export const usesCheck: IntraUnitCheck = {
  code: "USES",
  run(lu: LoadedUnit): readonly Finding[] {
    const findings: Finding[] = [];
    for (const step of lu.unit.steps) {
      if (step.uses.length === 0) continue;
      const declared = new Set<string>([
        ...(step.meta?.knowledge ?? []).map(base),
        ...(step.meta?.templates ?? []).map(base),
      ]);
      for (const u of step.uses) {
        if (!declared.has(base(u))) {
          findings.push(
            error(
              "USES",
              `step "${step.id}": [_uses: ${u}] is not declared in the step's meta _knowledge/_templates (declared: ${[...declared].join(", ") || "none"})`,
              { file: lu.file, path: `Step:${step.id}` },
            ),
          );
        }
      }
    }
    return findings;
  },
};
