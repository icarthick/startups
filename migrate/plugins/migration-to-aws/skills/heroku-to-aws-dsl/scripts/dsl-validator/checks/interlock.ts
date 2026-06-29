// scripts/dsl-validator/checks/interlock.ts
//
// Intra-unit check: a phase's _re_entry_guard.action must be a STOP action
// (_halt_and_inform / _unrecoverable). A CONTINUE action (_warn_and_skip etc.)
// would let the run proceed and defeat the fail-closed interlock. Uses the
// Tier-1 ERROR_ACTION_SEMANTICS control field (the payoff of that table).

import { type IntraUnitCheck, type LoadedUnit } from "./check.ts";
import { ERROR_ACTION_SEMANTICS } from "../types/error-action.ts";
import { type Finding, error } from "../findings.ts";

export const interlockCheck: IntraUnitCheck = {
  code: "INTERLOCK",
  run(lu: LoadedUnit): readonly Finding[] {
    if (lu.unit.kind !== "phase") return [];
    const guard = lu.unit.frontmatter.reEntryGuard;
    if (!guard) return [];
    const control = ERROR_ACTION_SEMANTICS[guard.action.kind].control;
    if (control !== "STOP") {
      return [
        error(
          "INTERLOCK",
          `_re_entry_guard.action "${guard.action.kind}" is a ${control} action — a re-run interlock must STOP (use _halt_and_inform or _unrecoverable)`,
          { file: lu.file, path: "_re_entry_guard.action" },
        ),
      ];
    }
    return [];
  },
};
