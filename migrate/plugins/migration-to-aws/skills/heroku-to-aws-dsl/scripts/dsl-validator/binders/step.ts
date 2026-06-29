// scripts/dsl-validator/binders/step.ts
//
// Body binder: a StepSection (id + raw body) -> Step. Splits the body into the
// optional ```meta``` fence + the prose after it, binds the meta, and extracts
// the [_uses: F] markers from the prose (the checkable projection).

import { type Step } from "../types/step.ts";
import { type StepSection } from "../parser/split.ts";
import { type Finding, type Location, type Result, error, fail, ok } from "../findings.ts";
import { bindMeta, extractMetaText } from "./meta.ts";

const META_FENCE_RE = /```meta\n[\s\S]*?\n```/;
const USES_RE = /\[_uses:\s*([^\]]+)\]/g;

/** Extract the [_uses: F] markers from prose (deduped, in order of first appearance). */
function extractUses(prose: string): string[] {
  // ignore markers inside fenced code blocks
  const proseNoCode = prose.replace(/```[\s\S]*?```/g, "");
  const seen = new Set<string>();
  const out: string[] = [];
  for (const m of proseNoCode.matchAll(USES_RE)) {
    const f = m[1].trim();
    if (!seen.has(f)) { seen.add(f); out.push(f); }
  }
  return out;
}

export function bindStep(section: StepSection, loc: Location): Result<Step> {
  const stepLoc: Location = { ...loc, line: section.line, path: `Step:${section.id}` };
  const f: Finding[] = [];

  const metaText = extractMetaText(section.body);
  let meta: Step["meta"] | undefined;
  if (metaText !== null) {
    const r = bindMeta(metaText, stepLoc);
    if (r.ok) meta = r.value; else f.push(...r.findings);
  }

  // prose = everything after the meta fence (or the whole body if no meta).
  const prose = section.body.replace(META_FENCE_RE, "").trim();
  if (prose === "") f.push(error("BIND", `step "${section.id}" has no reason prose`, stepLoc));

  const uses = extractUses(prose);

  if (f.length > 0) return fail(...f);

  return ok({
    id: section.id,
    ...(meta !== undefined ? { meta } : {}),
    prose,
    uses,
  });
}
