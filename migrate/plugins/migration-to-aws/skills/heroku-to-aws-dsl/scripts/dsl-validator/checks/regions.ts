// scripts/dsl-validator/checks/regions.ts
//
// Intra-unit check: the "Unit file regions" step-count rule (INTERPRETER 417-420).
//   - a PHASE has ZERO steps (its work is _fragments/_assemble in frontmatter);
//   - a FRAGMENT/ASSEMBLER has ONE OR MORE steps.
// (Trailing content + orientation position are handled in the splitter/bindUnit;
// kind-match is structurally guaranteed by bindUnit, so it cannot fire here.)

import { type IntraUnitCheck, type LoadedUnit } from "./check.ts";
import { type Finding, error } from "../findings.ts";

export const regionsCheck: IntraUnitCheck = {
  code: "REGIONS",
  run(lu: LoadedUnit): readonly Finding[] {
    const { unit, file } = lu;
    const n = unit.steps.length;
    if (unit.kind === "phase" && n > 0) {
      return [error("REGIONS", `a phase must have ZERO steps (its work is _fragments/_assemble), found ${n}`, { file })];
    }
    if (unit.kind !== "phase" && n === 0) {
      return [error("REGIONS", `a ${unit.kind} must have at least one step`, { file })];
    }
    return [];
  },
};
