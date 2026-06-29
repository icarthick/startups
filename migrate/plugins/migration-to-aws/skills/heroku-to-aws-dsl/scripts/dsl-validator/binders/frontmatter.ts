// scripts/dsl-validator/binders/frontmatter.ts
//
// Tier-3 composite binder: the parsed frontmatter map -> Frontmatter (one of three
// kinds). Detects the kind, enforces the per-kind closed vocabulary, and drives
// the Tier-2 binders over each list (_preconditions[], _knowledge[], _fragments[]
// ...), accumulating findings.
//
// Kind detection precedence: _phase > _fragment > _assemble (a phase also has
// _assemble, but as a {_file} map ref, not an id — _phase wins first).

import {
  type Frontmatter,
  type PhaseFrontmatter,
  type FragmentFrontmatter,
  type AssemblerFrontmatter,
  type UnitFrontmatterCore,
  type InitBlock,
} from "../types/frontmatter.ts";
import { type Condition } from "../types/condition.ts";
import { type Guarded } from "../types/guarded.ts";
import { type FragmentRef } from "../types/fragment-ref.ts";
import { type YamlValue } from "../parser/yaml.ts";
import { type Finding, type Location, type Result, error, fail, ok } from "../findings.ts";
import { bindList, isPlainObject } from "./shared.ts";
import { bindCondition } from "./condition.ts";
import { bindGuarded } from "./guarded.ts";
import { bindFragmentRef } from "./fragment-ref.ts";
import { bindReEntryGuard } from "./re-entry-guard.ts";
import { bindOnErrorTable } from "./on-error-table.ts";
import { bindAssemblerRef } from "./assembler-ref.ts";

// --- per-kind closed vocabularies (the grammar — derived from the type fields) ---
const PHASE_KEYS = new Set([
  "_phase", "_title", "_requires_phase", "_scope", "_init", "_re_entry_guard", "_input",
  "_preconditions", "_knowledge", "_templates", "_fragments", "_assemble",
  "_postconditions", "_produces", "_advances_to", "_forbids_files", "_on_error",
]);
const FRAGMENT_KEYS = new Set([
  "_fragment", "_of_phase", "_scope", "_produces", "_preconditions", "_postconditions", "_on_error",
]);
const ASSEMBLER_KEYS = new Set([
  "_assemble", "_of_phase", "_scope", "_reads", "_mutates", "_produces", "_postconditions", "_on_error",
]);

function asStr(v: YamlValue): string | null {
  return typeof v === "string" ? v : null;
}
function asStrListOrEmpty(v: YamlValue | undefined): readonly string[] | null {
  if (v === undefined) return [];
  if (Array.isArray(v) && v.every((x) => typeof x === "string")) return v as readonly string[];
  return null;
}

// ---------------------------------------------------------------------------

export function bindFrontmatter(yaml: YamlValue, loc: Location): Result<Frontmatter> {
  if (!isPlainObject(yaml)) return fail(error("BIND", `frontmatter must be a map`, loc));
  if ("_phase" in yaml) return bindPhase(yaml, loc);
  if ("_fragment" in yaml) return bindFragment(yaml, loc);
  if ("_assemble" in yaml) return bindAssembler(yaml, loc);
  return fail(error("BIND", `frontmatter has no unit-identity key (_phase / _fragment / _assemble)`, loc));
}

// --- closed-vocab helper ---
function checkVocab(yaml: { readonly [k: string]: YamlValue }, allowed: ReadonlySet<string>, loc: Location): Finding[] {
  return Object.keys(yaml)
    .filter((k) => !allowed.has(k))
    .map((k) => error("CLOSED_VOCAB", `unexpected key "${k}" in frontmatter`, loc));
}

// ---------------------------------------------------------------------------
// Phase
// ---------------------------------------------------------------------------

function bindPhase(yaml: { readonly [k: string]: YamlValue }, loc: Location): Result<Frontmatter> {
  const f: Finding[] = checkVocab(yaml, PHASE_KEYS, loc);

  const phase = asStr(yaml._phase);
  if (phase === null) f.push(error("BIND", `_phase must be a string`, loc));

  // _requires_phase: string | null (required key, value may be null)
  if (!("_requires_phase" in yaml)) f.push(error("BIND", `_phase frontmatter requires _requires_phase (string or null)`, loc));
  const requiresPhase = yaml._requires_phase === null ? null : asStr(yaml._requires_phase);
  if (yaml._requires_phase !== null && requiresPhase === null && "_requires_phase" in yaml) {
    f.push(error("BIND", `_requires_phase must be a string or null`, loc));
  }

  const scope = asStr(yaml._scope);
  if (scope === null) f.push(error("BIND", `_scope must be a string`, loc));

  const advancesTo = asStr(yaml._advances_to);
  if (advancesTo === null) f.push(error("BIND", `_advances_to must be a string`, loc));

  const input = asStrListOrEmpty(yaml._input);
  if (input === null) f.push(error("BIND", `_input must be a list of strings`, loc));

  const produces = asStrListOrEmpty(yaml._produces);
  if (produces === null) f.push(error("BIND", `_produces must be a list of strings`, loc));

  // optional lists via Tier-2 binders
  let preconditions: readonly Condition[] | undefined;
  if ("_preconditions" in yaml) {
    const r = bindList(yaml._preconditions, (it) => bindCondition(it, "pre", loc), "_preconditions", loc);
    if (r.ok) preconditions = r.value; else f.push(...r.findings);
  }
  let postconditions: readonly Condition[] | undefined;
  if ("_postconditions" in yaml) {
    const r = bindList(yaml._postconditions, (it) => bindCondition(it, "post", loc), "_postconditions", loc);
    if (r.ok) postconditions = r.value; else f.push(...r.findings);
  }
  let knowledge: readonly Guarded[] | undefined;
  if ("_knowledge" in yaml) {
    const r = bindList(yaml._knowledge, (it) => bindGuarded(it, "knowledge", loc), "_knowledge", loc);
    if (r.ok) knowledge = r.value; else f.push(...r.findings);
  }
  let templates: readonly Guarded[] | undefined;
  if ("_templates" in yaml) {
    const r = bindList(yaml._templates, (it) => bindGuarded(it, "template", loc), "_templates", loc);
    if (r.ok) templates = r.value; else f.push(...r.findings);
  }
  let fragments: readonly FragmentRef[] = [];
  {
    if (!("_fragments" in yaml)) f.push(error("BIND", `_phase frontmatter requires _fragments`, loc));
    else {
      const r = bindList(yaml._fragments, (it) => bindFragmentRef(it, loc), "_fragments", loc);
      if (r.ok) fragments = r.value; else f.push(...r.findings);
    }
  }

  // _assemble (phase ref), _on_error, _re_entry_guard?, _init?
  let assemble: PhaseFrontmatter["assemble"] | undefined;
  if (!("_assemble" in yaml)) f.push(error("BIND", `_phase frontmatter requires _assemble`, loc));
  else {
    const r = bindAssemblerRef(yaml._assemble, loc);
    if (r.ok) assemble = r.value; else f.push(...r.findings);
  }

  let onError: PhaseFrontmatter["onError"] | undefined;
  if (!("_on_error" in yaml)) f.push(error("BIND", `_phase frontmatter requires _on_error`, loc));
  else {
    const r = bindOnErrorTable(yaml._on_error, loc);
    if (r.ok) onError = r.value; else f.push(...r.findings);
  }

  let reEntryGuard: PhaseFrontmatter["reEntryGuard"] | undefined;
  if ("_re_entry_guard" in yaml) {
    const r = bindReEntryGuard(yaml._re_entry_guard, loc);
    if (r.ok) reEntryGuard = r.value; else f.push(...r.findings);
  }

  let init: InitBlock | undefined;
  if ("_init" in yaml) {
    init = isPlainObject(yaml._init) ? { verbs: yaml._init } : { verbs: {} };
  }

  const forbidsFiles = asStrListOrEmpty(yaml._forbids_files);
  if (forbidsFiles === null) f.push(error("BIND", `_forbids_files must be a list of strings`, loc));

  if (f.length > 0 || phase === null || scope === null || advancesTo === null
    || input === null || produces === null || assemble === undefined || onError === undefined) {
    if (f.length === 0) f.push(error("BIND", `phase frontmatter could not be bound`, loc));
    return fail(...f);
  }

  const pf: PhaseFrontmatter = {
    kind: "phase", phase, requiresPhase, scope, input, fragments, assemble, produces, advancesTo, onError,
    ...(yaml._title !== undefined && typeof yaml._title === "string" ? { title: yaml._title } : {}),
    ...(init !== undefined ? { init } : {}),
    ...(reEntryGuard !== undefined ? { reEntryGuard } : {}),
    ...(preconditions !== undefined ? { preconditions } : {}),
    ...(knowledge !== undefined ? { knowledge } : {}),
    ...(templates !== undefined ? { templates } : {}),
    ...(postconditions !== undefined ? { postconditions } : {}),
    ...(forbidsFiles && forbidsFiles.length > 0 ? { forbidsFiles } : {}),
  };
  return ok(pf);
}

// ---------------------------------------------------------------------------
// Fragment / Assembler — share UnitFrontmatterCore.
// ---------------------------------------------------------------------------

/**
 * Bind the keys shared by fragment + assembler frontmatter (_of_phase, _scope,
 * _produces, _preconditions?, _postconditions, _on_error). Accumulates findings
 * into `f`; returns the core or undefined if a required piece is missing.
 */
function bindUnitCore(
  yaml: { readonly [k: string]: YamlValue },
  f: Finding[],
  loc: Location,
): UnitFrontmatterCore | undefined {
  const ofPhase = asStr(yaml._of_phase);
  if (ofPhase === null) f.push(error("BIND", `_of_phase must be a string`, loc));
  const scope = asStr(yaml._scope);
  if (scope === null) f.push(error("BIND", `_scope must be a string`, loc));

  const produces = asStrListOrEmpty(yaml._produces);
  if (produces === null) f.push(error("BIND", `_produces must be a list of strings`, loc));

  let preconditions: readonly Condition[] | undefined;
  if ("_preconditions" in yaml) {
    const r = bindList(yaml._preconditions, (it) => bindCondition(it, "pre", loc), "_preconditions", loc);
    if (r.ok) preconditions = r.value; else f.push(...r.findings);
  }

  let postconditions: readonly Condition[] = [];
  if (!("_postconditions" in yaml)) f.push(error("BIND", `unit frontmatter requires _postconditions`, loc));
  else {
    const r = bindList(yaml._postconditions, (it) => bindCondition(it, "post", loc), "_postconditions", loc);
    if (r.ok) postconditions = r.value; else f.push(...r.findings);
  }

  let onError: UnitFrontmatterCore["onError"] | undefined;
  if (!("_on_error" in yaml)) f.push(error("BIND", `unit frontmatter requires _on_error`, loc));
  else {
    const r = bindOnErrorTable(yaml._on_error, loc);
    if (r.ok) onError = r.value; else f.push(...r.findings);
  }

  if (ofPhase === null || scope === null || produces === null || onError === undefined) return undefined;
  return {
    ofPhase, scope, produces, postconditions, onError,
    ...(preconditions !== undefined ? { preconditions } : {}),
  };
}

function bindFragment(yaml: { readonly [k: string]: YamlValue }, loc: Location): Result<Frontmatter> {
  const f: Finding[] = checkVocab(yaml, FRAGMENT_KEYS, loc);
  const fragment = asStr(yaml._fragment);
  if (fragment === null) f.push(error("BIND", `_fragment must be a string`, loc));
  const core = bindUnitCore(yaml, f, loc);
  if (f.length > 0 || fragment === null || core === undefined) {
    if (f.length === 0) f.push(error("BIND", `fragment frontmatter could not be bound`, loc));
    return fail(...f);
  }
  const ff: FragmentFrontmatter = { kind: "fragment", fragment, ...core };
  return ok(ff);
}

function bindAssembler(yaml: { readonly [k: string]: YamlValue }, loc: Location): Result<Frontmatter> {
  const f: Finding[] = checkVocab(yaml, ASSEMBLER_KEYS, loc);
  const assemble = asStr(yaml._assemble);
  if (assemble === null) f.push(error("BIND", `_assemble (assembler id) must be a string`, loc));

  // _reads / _mutates: optional string lists
  let reads: readonly string[] | undefined;
  if ("_reads" in yaml) {
    const r = asStrListOrEmpty(yaml._reads);
    if (r === null) f.push(error("BIND", `_reads must be a list of strings`, loc)); else reads = r;
  }
  let mutates: readonly string[] | undefined;
  if ("_mutates" in yaml) {
    const r = asStrListOrEmpty(yaml._mutates);
    if (r === null) f.push(error("BIND", `_mutates must be a list of strings`, loc)); else mutates = r;
  }

  const core = bindUnitCore(yaml, f, loc);
  if (f.length > 0 || assemble === null || core === undefined) {
    if (f.length === 0) f.push(error("BIND", `assembler frontmatter could not be bound`, loc));
    return fail(...f);
  }
  const af: AssemblerFrontmatter = {
    kind: "assembler", assemble, ...core,
    ...(reads !== undefined ? { reads } : {}),
    ...(mutates !== undefined ? { mutates } : {}),
  };
  return ok(af);
}
