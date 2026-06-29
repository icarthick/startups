// scripts/dsl-validator/binders/unit.ts
//
// Tier-4 apex binder: a whole .md file -> Unit. Splits the file into regions
// (splitUnitFile), binds the frontmatter + orientation + each step, and assembles
// the typed Unit whose kind matches the frontmatter kind.
//
// This is the parser's front door: text in, typed Unit (or Findings) out — the
// input the check layer consumes.

import { type Unit, type UnitRegions } from "../types/unit.ts";
import { type Step } from "../types/step.ts";
import { type Orientation } from "../types/orientation.ts";
import { splitUnitFile, SplitError } from "../parser/split.ts";
import { parseYaml, YamlParseError } from "../parser/yaml.ts";
import { type Finding, type Location, type Result, error, fail, ok } from "../findings.ts";
import { bindFrontmatter } from "./frontmatter.ts";
import { bindOrientation } from "./orientation.ts";
import { bindStep } from "./step.ts";

export function bindUnit(text: string, file: string): Result<Unit> {
  const loc: Location = { file };

  // 1. structural split (throws only on no-frontmatter-fence)
  let split;
  try {
    split = splitUnitFile(text);
  } catch (e) {
    if (e instanceof SplitError) return fail(error("REGIONS", e.message, { file, line: e.line }));
    throw e;
  }

  const f: Finding[] = [];

  // 2. frontmatter (its own YAML parse can throw)
  let frontmatter;
  try {
    const fmYaml = parseYaml(split.frontmatterText);
    const r = bindFrontmatter(fmYaml, loc);
    if (r.ok) frontmatter = r.value; else f.push(...r.findings);
  } catch (e) {
    if (e instanceof YamlParseError) f.push(error("YAML", e.message, { file, line: e.line }));
    else throw e;
  }

  // 3. orientation (optional)
  let orientation: Orientation | undefined;
  if (split.orientation !== undefined) {
    const r = bindOrientation(split.orientation, loc);
    if (r.ok) orientation = r.value; else f.push(...r.findings);
  }

  // 4. steps
  const steps: Step[] = [];
  for (const section of split.steps) {
    const r = bindStep(section, loc);
    if (r.ok) steps.push(r.value); else f.push(...r.findings);
  }

  // 5. trailing content is a regions violation
  if (split.trailing !== undefined) {
    f.push(error("REGIONS", `content after the last step/orientation is forbidden: ${split.trailing.slice(0, 60)}...`, loc));
  }

  if (f.length > 0 || frontmatter === undefined) {
    if (f.length === 0) f.push(error("BIND", `unit could not be bound`, loc));
    return fail(...f);
  }

  const regions: UnitRegions = {
    ...(split.title !== undefined ? { title: split.title } : {}),
    ...(orientation !== undefined ? { orientation } : {}),
    steps,
  };

  // 6. assemble the typed Unit, kind matching the frontmatter (the discriminants
  //    are guaranteed consistent because the unit kind IS the frontmatter kind).
  switch (frontmatter.kind) {
    case "phase":
      return ok({ kind: "phase", frontmatter, ...regions });
    case "fragment":
      return ok({ kind: "fragment", frontmatter, ...regions });
    case "assembler":
      return ok({ kind: "assembler", frontmatter, ...regions });
  }
}
