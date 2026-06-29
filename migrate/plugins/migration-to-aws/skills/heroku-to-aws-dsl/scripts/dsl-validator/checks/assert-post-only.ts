// scripts/dsl-validator/checks/assert-post-only.ts
//
// Intra-unit check: `_assert` may appear ONLY in _postconditions (it has an
// implicit default-halt and post semantics). A precondition Condition whose verb
// is _assert is a violation. (The Condition already carries its context tag.)

import { type IntraUnitCheck, type LoadedUnit } from "./check.ts";
import { type Condition } from "../types/condition.ts";
import { type Finding, error } from "../findings.ts";

function preconditionsOf(lu: LoadedUnit): readonly Condition[] {
  const fm = lu.unit.frontmatter;
  return fm.preconditions ?? [];
}

export const assertPostOnlyCheck: IntraUnitCheck = {
  code: "BIND",
  run(lu: LoadedUnit): readonly Finding[] {
    const findings: Finding[] = [];
    for (const c of preconditionsOf(lu)) {
      if (c.verb.kind === "_assert") {
        findings.push(error("BIND", `_assert may only appear in _postconditions, not _preconditions`, { file: lu.file }));
      }
    }
    return findings;
  },
};
