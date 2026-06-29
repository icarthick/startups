// scripts/dsl-validator/binders/meta.ts
//
// Body binder: a step's ```meta``` block -> Meta. The meta fence is YAML, so:
// extract it, parseYaml it, then bind the 10 FORM-2b meta keys. Flags FORM-1-only
// keys (_cases/_default/_steps) as FORM1_LEAK and unknown _-keys as CLOSED_VOCAB.
//
// _knowledge/_templates here are uses-annotations (string[], NOT Guarded).
// _when reuses bindWhenCondition (the fourth _when context).

import { type Meta, META_KEYS, FORM1_ONLY_META_KEYS } from "../types/meta.ts";
import { parseYaml, YamlParseError, type YamlValue } from "../parser/yaml.ts";
import { type Finding, type Location, type Result, error, fail, ok } from "../findings.ts";
import { asStrList, isPlainObject } from "./shared.ts";
import { bindWhenCondition } from "./when-condition.ts";

const META_FENCE_RE = /```meta\n([\s\S]*?)\n```/;

/** Extract the raw meta-fence text from a step body, or null if there is none. */
export function extractMetaText(stepBody: string): string | null {
  const m = stepBody.match(META_FENCE_RE);
  return m ? m[1] : null;
}

export function bindMeta(metaText: string, loc: Location): Result<Meta> {
  let yaml: YamlValue;
  try {
    yaml = parseYaml(metaText);
  } catch (e) {
    if (e instanceof YamlParseError) return fail(error("YAML", e.message, { ...loc, line: e.line }));
    throw e;
  }
  if (!isPlainObject(yaml)) return fail(error("BIND", `a meta block must be a map`, loc));

  const f: Finding[] = [];

  // vocabulary: FORM-1 leaks + unknown keys
  for (const k of Object.keys(yaml)) {
    if (FORM1_ONLY_META_KEYS.includes(k)) f.push(error("FORM1_LEAK", `FORM-1-only key "${k}" in a FORM-2b meta block`, loc));
    else if (!META_KEYS.includes(k)) f.push(error("CLOSED_VOCAB", `unknown meta key "${k}"`, loc));
  }

  const strList = (key: string): readonly string[] | undefined => {
    if (!(key in yaml)) return undefined;
    const r = asStrList(yaml[key]);
    if (r === null) { f.push(error("BIND", `meta "${key}" must be a string or list of strings`, loc)); return undefined; }
    return r;
  };
  const str = (key: string): string | undefined => {
    if (!(key in yaml)) return undefined;
    if (typeof yaml[key] !== "string") { f.push(error("BIND", `meta "${key}" must be a string`, loc)); return undefined; }
    return yaml[key] as string;
  };

  const knowledge = strList("_knowledge");
  const templates = strList("_templates");
  const forEach = str("_for_each");
  const branchOn = str("_branch_on");
  const branchCases = strList("_branch_cases");
  const collect = strList("_collect");
  const writes = strList("_writes");
  const writesVar = str("_writes_var");
  const reads = strList("_reads");
  const mutates = strList("_mutates");

  let when: Meta["when"] | undefined;
  if ("_when" in yaml) {
    const r = bindWhenCondition(yaml._when, { ...loc, path: "_when" });
    if (r.ok) when = r.value; else f.push(...r.findings);
  }

  if (f.length > 0) return fail(...f);

  return ok({
    ...(knowledge !== undefined ? { knowledge } : {}),
    ...(templates !== undefined ? { templates } : {}),
    ...(forEach !== undefined ? { forEach } : {}),
    ...(branchOn !== undefined ? { branchOn } : {}),
    ...(branchCases !== undefined ? { branchCases } : {}),
    ...(collect !== undefined ? { collect } : {}),
    ...(writes !== undefined ? { writes } : {}),
    ...(writesVar !== undefined ? { writesVar } : {}),
    ...(reads !== undefined ? { reads } : {}),
    ...(mutates !== undefined ? { mutates } : {}),
    ...(when !== undefined ? { when } : {}),
  });
}
