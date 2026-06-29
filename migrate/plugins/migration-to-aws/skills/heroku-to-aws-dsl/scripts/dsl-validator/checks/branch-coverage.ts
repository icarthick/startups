// scripts/dsl-validator/checks/branch-coverage.ts
//
// Intra-unit check: a step that branches (`_branch_on`) MUST declare the
// discriminant values its prose arms cover (`_branch_cases`). FORM-2b case bodies
// are prose, so the validator can't read them — but it CAN check the author
// declared the coverage set. A `_branch_on` without `_branch_cases` is an
// unverifiable branch: the exact silent-drop class that bit the old design.py
// (dropped SG 3D/3E, empty-Procfile reject, rds_proxy, kafka-broker-by-tier).
// Declaring the cases makes coverage a checkable, reviewable list.

import { type IntraUnitCheck, type LoadedUnit } from "./check.ts";
import { type Finding, error } from "../findings.ts";

export const branchCoverageCheck: IntraUnitCheck = {
  code: "BRANCH_COVERAGE",
  run(lu: LoadedUnit): readonly Finding[] {
    const findings: Finding[] = [];
    for (const step of lu.unit.steps) {
      const m = step.meta;
      if (!m?.branchOn) continue;
      if (!m.branchCases || m.branchCases.length === 0) {
        findings.push(
          error(
            "BRANCH_COVERAGE",
            `step "${step.id}" has _branch_on="${m.branchOn}" but no _branch_cases — the prose arms are unverifiable; declare the discriminant values covered (include _default for a catch-all)`,
            { file: lu.file, path: `Step:${step.id}` },
          ),
        );
      }
    }
    return findings;
  },
};
