// scripts/dsl-validator/validate.ts
//
// Orchestrator + CLI. The validator's front door: discover all unit files in a
// skill root, bind each to a typed Unit (collecting bind-time Findings), run the
// full check suite over the bound units, and report. Exits non-zero on any error
// (warnings do not fail unless --strict).
//
// Run:  node scripts/dsl-validator/validate.ts <skill-root> [--strict]

import { readFileSync, readdirSync, existsSync } from "node:fs";
import { type Finding } from "./findings.ts";
import { bindUnit } from "./binders/unit.ts";
import { runChecks, type LoadedUnit } from "./checks/check.ts";
import { regionsCheck } from "./checks/regions.ts";
import { usesCheck } from "./checks/uses.ts";
import { assertPostOnlyCheck } from "./checks/assert-post-only.ts";
import { interlockCheck } from "./checks/interlock.ts";
import { branchCoverageCheck } from "./checks/branch-coverage.ts";
import { fragmentRefCheck } from "./checks/fragment-ref.ts";
import { subsetCheck } from "./checks/subset.ts";
import { guardScopeCheck } from "./checks/guard-scope.ts";
import { producesCheck } from "./checks/produces.ts";
import { phaseChainCheck } from "./checks/phase-chain.ts";
import { makeXtableCheck } from "./checks/xtable.ts";
import { makeRefResolveCheck } from "./checks/ref-resolve.ts";

/** Discover every unit file under <root>/phases: the phase files + nested units. */
export function discoverUnitFiles(root: string): string[] {
  const phasesDir = `${root}/phases`;
  if (!existsSync(phasesDir)) return [];
  const files: string[] = [];
  for (const entry of readdirSync(phasesDir, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      for (const f of readdirSync(`${phasesDir}/${entry.name}`)) {
        if (f.endsWith(".md")) files.push(`phases/${entry.name}/${f}`);
      }
    } else if (entry.name.endsWith(".phase.md")) {
      files.push(`phases/${entry.name}`);
    }
  }
  return files.sort();
}

/** Bind all files + run all checks. Returns every Finding (bind-time + check). */
export function validate(root: string): readonly Finding[] {
  const findings: Finding[] = [];
  const loaded: LoadedUnit[] = [];

  for (const rel of discoverUnitFiles(root)) {
    const r = bindUnit(readFileSync(`${root}/${rel}`, "utf8"), rel);
    if (r.ok) loaded.push({ file: rel, unit: r.value });
    else findings.push(...r.findings);
  }

  const intra = [regionsCheck, usesCheck, assertPostOnlyCheck, interlockCheck, branchCoverageCheck];
  const cross = [fragmentRefCheck, subsetCheck, guardScopeCheck, producesCheck, phaseChainCheck, makeXtableCheck(root), makeRefResolveCheck(root)];
  findings.push(...runChecks(loaded, intra, cross));

  return findings;
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

function main(): void {
  const args = process.argv.slice(2);
  const strict = args.includes("--strict");
  const root = args.find((a) => !a.startsWith("-")) ?? ".";

  const findings = validate(root);
  const errors = findings.filter((f) => f.severity === "error");
  const warnings = findings.filter((f) => f.severity === "warning");

  const fileCount = discoverUnitFiles(root).length;
  console.log(`DSL validator: ${fileCount} unit files`);

  for (const f of findings) {
    const loc = f.location.line ? `${f.location.file}:${f.location.line}` : f.location.file;
    const tag = f.severity === "error" ? "ERROR" : "WARN ";
    console.log(`  ${tag} [${f.code}] ${loc}${f.location.path ? ` (${f.location.path})` : ""}: ${f.message}`);
  }

  const hardFail = errors.length + (strict ? warnings.length : 0);
  if (hardFail > 0) {
    console.log(`FAIL: ${errors.length} error(s)${strict ? `, ${warnings.length} warning(s) (strict)` : `; ${warnings.length} warning(s)`}`);
    process.exit(1);
  }
  console.log(warnings.length > 0 ? `OK (${warnings.length} warning(s))` : "OK");
}

main();
