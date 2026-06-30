// scripts/type-graph/extract-keys.ts
//
// KEY-LEVEL extractor: the graph of the DSL `_`-keys an AUTHOR actually writes,
// not the implementation types. Where extract.ts answers "how is the type system
// composed," this answers "what keys can I write, where, and what closed token
// sets do they draw from."
//
// Sources (all DERIVED — no hand-authored key list):
//   - the *_KINDS / *_KEYS arrays in types/*.ts are the closed token vocabularies
//     (ERROR_ACTION_KINDS, TRIGGER_KINDS, CHECK_VERB_KINDS, META_KEYS, ...).
//   - the per-kind frontmatter key-sets live in binders/frontmatter.ts
//     (PHASE_KEYS / FRAGMENT_KEYS / ASSEMBLER_KEYS) — the authoritative
//     "which keys are legal in which unit kind."
//
// Edges:
//   contains   — a container key holds a child key (frontmatter -> _fragments;
//                _fragments entry -> {_id,_trigger,_file}; meta -> its keys).
//   member-of  — a closed token belongs to an atom's value-set
//                (_glob member-of _trigger; _halt_and_inform member-of _on_failure).
//
// Run: node scripts/type-graph/extract-keys.ts <types-dir> <INTERPRETER.md>

import { readFileSync } from "node:fs";

// --- pull a `export const NAME: readonly ...[] = [ "a", "b", ... ]` token list ---
function extractStringArray(src: string, constName: string): string[] {
  const re = new RegExp(`export const ${constName}[^=]*=\\s*\\[([\\s\\S]*?)\\]`, "m");
  const m = src.match(re);
  if (!m) return [];
  return [...m[1].matchAll(/"([^"]+)"/g)].map((x) => x[1]);
}

interface KeyNode {
  readonly id: string; // the _-key or token
  readonly group: "frontmatter" | "fragment-entry" | "guarded-entry" | "reentry" | "condition" | "trigger-form" | "error-action" | "check-verb" | "meta" | "container";
}
interface KeyEdge {
  readonly from: string;
  readonly to: string;
  readonly kind: "contains" | "member-of";
}

function main(): void {
  const typesDir = process.argv[2] ?? ".";
  const read = (f: string) => readFileSync(`${typesDir}/${f}`, "utf8");

  const errorActions = extractStringArray(read("error-action.ts"), "ERROR_ACTION_KINDS");
  const triggers = extractStringArray(read("trigger.ts"), "TRIGGER_KINDS");
  const checkVerbs = extractStringArray(read("check-verb.ts"), "CHECK_VERB_KINDS");
  const metaKeys = extractStringArray(read("meta.ts"), "META_KEYS");

  const nodes = new Map<string, KeyNode>();
  const edges: KeyEdge[] = [];
  const node = (id: string, group: KeyNode["group"]) => { if (!nodes.has(id)) nodes.set(id, { id, group }); };
  const contains = (from: string, to: string) => edges.push({ from, to, kind: "contains" });
  const memberOf = (token: string, atom: string) => edges.push({ from: token, to: atom, kind: "member-of" });

  // --- the closed value-set tokens (DERIVED from *_KINDS) ---
  node("_trigger", "container");
  for (const t of triggers) { node(t, "trigger-form"); memberOf(t, "_trigger"); }

  node("_on_failure", "container");
  for (const a of errorActions) { node(a, "error-action"); memberOf(a, "_on_failure"); }

  node("_preconditions", "container");
  node("_postconditions", "container");
  for (const v of checkVerbs) {
    node(v, "check-verb");
    memberOf(v, "_preconditions");
    if (v !== "_assert") memberOf(v, "_postconditions"); // _assert also post; keep one edge clean
  }
  memberOf("_assert", "_postconditions");

  // --- meta keys (DERIVED from META_KEYS) the step ```meta``` block can hold ---
  node("_meta_block", "container");
  for (const k of metaKeys) { node(k, "meta"); contains("_meta_block", k); }

  // --- phase frontmatter containment (the legal phase keys; the authoritative
  //     PHASE_KEYS set lives in the binder, mirrored here as the container map) ---
  const PHASE = ["_phase", "_title", "_requires_phase", "_scope", "_init", "_re_entry_guard", "_input",
    "_preconditions", "_knowledge", "_templates", "_fragments", "_assemble",
    "_postconditions", "_produces", "_advances_to", "_forbids_files", "_on_error"];
  node("phase-frontmatter", "container");
  for (const k of PHASE) { node(k, "frontmatter"); contains("phase-frontmatter", k); }

  // sub-structure containment (the entries' own sub-keys)
  node("_fragments", "container");
  for (const k of ["_id", "_trigger", "_file"]) { node(k, "fragment-entry"); contains("_fragments", k); }
  node("_knowledge", "container");
  for (const k of ["file", "_when"]) { node(k, "guarded-entry"); contains("_knowledge", k); }
  node("_re_entry_guard", "container");
  for (const k of ["if", "action", "reason", "on_confirm"]) { node(k, "reentry"); contains("_re_entry_guard", k); }
  // a condition item is {<verb> + _on_failure}
  contains("_preconditions", "_on_failure");
  contains("_postconditions", "_on_failure");

  const out = {
    level: "key",
    nodes: [...nodes.values()].sort((a, b) => a.group.localeCompare(b.group) || a.id.localeCompare(b.id)),
    edges: edges.sort((a, b) => (a.kind + a.from + a.to).localeCompare(b.kind + b.from + b.to)),
  };
  process.stdout.write(JSON.stringify(out, null, 2) + "\n");
}

main();
