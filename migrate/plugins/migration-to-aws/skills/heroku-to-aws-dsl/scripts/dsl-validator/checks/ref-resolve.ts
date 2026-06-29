// scripts/dsl-validator/checks/ref-resolve.ts
//
// Cross-unit check: REFERENCE RESOLUTION + JSON validity + orphan knowledge.
// The 22 unit files are bound + checked; this closes the gap on the files they
// POINT AT but the validator never confirmed exist or parse:
//
//   - _validate_schema { schema } refs (in any unit's pre/postconditions)
//   - phase _knowledge / _templates `file` refs (Guarded entries)
//
// For each ref: the named file (skill-root-relative path) MUST exist on disk; and
// a referenced .json file (knowledge or schema) MUST parse as JSON. Plus an
// ORPHAN sweep: every file under knowledge/ MUST be referenced by some phase
// _knowledge ref (an unreferenced knowledge file is dead data / a likely typo).
//
// Reads the filesystem, so — like xtable — it is a FACTORY over the skill root
// (it consumes bound Units AND the disk).
//
// Known non-goal: schema/template paths mentioned only inside `_assert` PROSE
// (e.g. "...validates against schemas/feedback-trace.schema.json") are NOT
// structured refs and are intentionally not resolved here — prose is not a
// machine contract.

import { type CrossUnitCheck, type LoadedUnit } from "./check.ts";
import { type Condition } from "../types/condition.ts";
import { type Finding, error } from "../findings.ts";
import { readFileSync, existsSync, readdirSync, statSync } from "node:fs";

/** Collect every file under <dir> recursively, as skill-root-relative paths. */
function walk(root: string, rel: string): string[] {
  const abs = `${root}/${rel}`;
  if (!existsSync(abs)) return [];
  const out: string[] = [];
  for (const entry of readdirSync(abs)) {
    const childRel = `${rel}/${entry}`;
    if (statSync(`${root}/${childRel}`).isDirectory()) out.push(...walk(root, childRel));
    else out.push(childRel);
  }
  return out;
}

function jsonParses(abs: string): boolean {
  try {
    JSON.parse(readFileSync(abs, "utf8"));
    return true;
  } catch {
    return false;
  }
}

/** Every _validate_schema verb across a unit's pre + postconditions. */
function schemaRefs(conds: readonly Condition[] | undefined): string[] {
  const out: string[] = [];
  for (const c of conds ?? []) {
    if (c.verb.kind === "_validate_schema") out.push(c.verb.schema);
  }
  return out;
}

/** Build the ref-resolution check bound to a skill root (it reads disk). */
export function makeRefResolveCheck(root: string): CrossUnitCheck {
  return {
    code: "REF_RESOLVE",
    run(units: readonly LoadedUnit[]): readonly Finding[] {
      const findings: Finding[] = [];

      // ----- the set of knowledge files actually referenced (for the orphan sweep) -----
      const referencedKnowledge = new Set<string>();

      for (const lu of units) {
        const fm = lu.unit.frontmatter;

        // ----- 1. _validate_schema schema refs (any unit kind) -----
        const conds: (readonly Condition[] | undefined)[] = [fm.preconditions, fm.postconditions];
        for (const schema of conds.flatMap(schemaRefs)) {
          const abs = `${root}/${schema}`;
          if (!existsSync(abs)) {
            findings.push(error("REF_RESOLVE", `_validate_schema names "${schema}" which does not exist`, { file: lu.file }));
          } else if (schema.endsWith(".json") && !jsonParses(abs)) {
            findings.push(error("JSON_INVALID", `schema "${schema}" is not valid JSON`, { file: lu.file }));
          }
        }

        // ----- 2. phase _knowledge / _templates file refs -----
        if (lu.unit.kind === "phase") {
          const pfm = lu.unit.frontmatter;
          for (const g of [...(pfm.knowledge ?? []), ...(pfm.templates ?? [])]) {
            const abs = `${root}/${g.file}`;
            if (g.role === "knowledge") referencedKnowledge.add(g.file);
            if (!existsSync(abs)) {
              findings.push(error("REF_RESOLVE", `_${g.role === "knowledge" ? "knowledge" : "templates"} names "${g.file}" which does not exist`, { file: lu.file }));
            } else if (g.role === "knowledge" && g.file.endsWith(".json") && !jsonParses(abs)) {
              findings.push(error("JSON_INVALID", `knowledge file "${g.file}" is not valid JSON`, { file: lu.file }));
            }
          }
        }
      }

      // ----- 3. orphan sweep: every knowledge/ file must be referenced -----
      for (const f of walk(root, "knowledge")) {
        if (!referencedKnowledge.has(f)) {
          findings.push(error("ORPHAN", `knowledge file "${f}" is not referenced by any phase _knowledge (dead data or a typo'd ref)`, { file: f }));
        }
      }

      return findings;
    },
  };
}
