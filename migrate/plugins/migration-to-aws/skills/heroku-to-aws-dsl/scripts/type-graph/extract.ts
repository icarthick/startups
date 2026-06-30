// scripts/type-graph/extract.ts
//
// Structural extractor: reads the DSL validator's types/*.ts and emits the
// composition graph (nodes + edges) DERIVED from the type definitions — the
// authoritative source. No hand-maintained edge list for the structural layer;
// change a field in types/, regenerate, the graph is correct.
//
// Zero-dep, Node-native TS type-strip ethos (same as the validator). We do NOT
// pull in the TS compiler API; instead we scan interface/type-alias declarations
// and resolve field/member type references against the known DSL node set. The
// scan is deliberately narrow: it only trusts references that resolve to a known
// DSL type (so stray identifiers like `string`/`Record` are ignored), which makes
// regex-level parsing safe here even though parsing arbitrary TS by regex is not.
//
// Run: node scripts/type-graph/extract.ts <validator-types-dir> > structural.json

import { readFileSync, readdirSync } from "node:fs";

// ---------------------------------------------------------------------------
// The closed node set — the 15 DSL types (the only identifiers we treat as edges).
// Tier + kind are fixed facts about the grammar, declared here (small, stable).
// Everything else (edges, degrees) is DERIVED from the source.
// ---------------------------------------------------------------------------

interface NodeMeta {
  readonly tier: 1 | 2 | 3 | 4;
  readonly kind: "value" | "entry" | "subdoc" | "unit";
}

const NODES: Record<string, NodeMeta> = {
  // Tier 1 — value atoms
  WhenCondition: { tier: 1, kind: "value" },
  ErrorAction: { tier: 1, kind: "value" },
  CheckVerb: { tier: 1, kind: "value" },
  Trigger: { tier: 1, kind: "value" },
  // Tier 2 — entries / clauses
  Condition: { tier: 2, kind: "entry" },
  Guarded: { tier: 2, kind: "entry" },
  FragmentRef: { tier: 2, kind: "entry" },
  AssemblerRef: { tier: 2, kind: "entry" },
  ReEntryGuard: { tier: 2, kind: "entry" },
  OnErrorTable: { tier: 2, kind: "entry" },
  // Tier 3 — sub-documents
  Meta: { tier: 3, kind: "subdoc" },
  Step: { tier: 3, kind: "subdoc" },
  Orientation: { tier: 3, kind: "subdoc" },
  Frontmatter: { tier: 3, kind: "subdoc" },
  // Tier 4 — unit (apex)
  Unit: { tier: 4, kind: "unit" },
};

// Frontmatter is one conceptual node, but the source splits it into three
// interfaces + a union. Members of these collapse onto `Frontmatter`. Likewise
// the unit kinds collapse onto `Unit`. This mapping keeps the graph type-level
// (15 nodes) rather than exposing every helper interface.
const ALIAS_TO_NODE: Record<string, string> = {
  PhaseFrontmatter: "Frontmatter",
  FragmentFrontmatter: "Frontmatter",
  AssemblerFrontmatter: "Frontmatter",
  UnitFrontmatterCore: "Frontmatter",
  Phase: "Unit",
  Fragment: "Unit",
  Assembler: "Unit",
  UnitRegions: "Unit",
};

// Identifiers that are real DSL nodes when referenced as a field type.
const REFERABLE = new Set<string>([...Object.keys(NODES), ...Object.keys(ALIAS_TO_NODE)]);

function canon(id: string): string | null {
  if (id in ALIAS_TO_NODE) return ALIAS_TO_NODE[id];
  if (id in NODES) return id;
  return null;
}

// ---------------------------------------------------------------------------
// Edge extraction.
//
// We scan each .ts file for the bodies of `interface X { ... }` and
// `type X = A | B | C` declarations, and for every reference to a REFERABLE
// identifier inside a body, record an edge X -> canon(ref). The owning
// declaration name X is also canonicalized (PhaseFrontmatter -> Frontmatter).
// ---------------------------------------------------------------------------

interface Edge {
  readonly from: string;
  readonly to: string;
  readonly kind: "field" | "member"; // field = interface field ref; member = union member
}

// Strip comments (line + block / JSDoc) before scanning. CRITICAL: comments
// routinely MENTION other types to DOCUMENT a NON-relationship (e.g. meta.ts:
// "distinct from the phase-level Guarded[]", "NOT Guarded"). Scanning comment
// text produces FALSE edges from exactly the prose that DENIES the edge. Only
// real type positions count. (A false `Meta -> Guarded` edge was caught by the
// very first graph render — the payoff of deriving from source, then trusting
// the diff against what we know to be true.)
function stripComments(s: string): string {
  return s
    .replace(/\/\*[\s\S]*?\*\//g, "") // block / JSDoc
    .replace(/\/\/[^\n]*/g, ""); // line
}

// Match referable identifiers as whole words (so `Trigger` matches but
// `TriggerKind` / `triggerish` do not). Comments are stripped first.
function refsIn(bodyRaw: string): Set<string> {
  const body = stripComments(bodyRaw);
  const found = new Set<string>();
  for (const id of REFERABLE) {
    const re = new RegExp(`\\b${id}\\b`, "g");
    if (re.test(body)) found.add(id);
  }
  return found;
}

function extractFile(src: string, edges: Edge[]): void {
  // Strip comments from the whole source FIRST so neither the declaration
  // matchers nor refsIn ever see commented-out code or doc-prose type mentions.
  src = stripComments(src);
  // interface declarations: `export interface X extends Y { ...body... }`
  // Capture the name, the optional extends clause, and the brace body.
  const ifaceRe = /export\s+interface\s+([A-Za-z0-9_]+)(\s+extends\s+([A-Za-z0-9_,\s]+))?\s*\{([\s\S]*?)\n\}/g;
  for (const m of src.matchAll(ifaceRe)) {
    const owner = canon(m[1]);
    if (!owner) continue;
    // extends clause -> structural edge (UnitFrontmatterCore feeds the frontmatters,
    // but both canonicalize to Frontmatter, so a self-edge is dropped below).
    const extendsClause = m[3] ?? "";
    const body = m[4] ?? "";
    for (const ref of refsIn(extendsClause + "\n" + body)) {
      const to = canon(ref);
      if (to && to !== owner) edges.push({ from: owner, to, kind: "field" });
    }
  }

  // type-alias unions: `export type X = A | B | C;`
  const aliasRe = /export\s+type\s+([A-Za-z0-9_]+)\s*=\s*([\s\S]*?);/g;
  for (const m of src.matchAll(aliasRe)) {
    const owner = canon(m[1]);
    if (!owner) continue;
    for (const ref of refsIn(m[2] ?? "")) {
      const to = canon(ref);
      if (to && to !== owner) edges.push({ from: owner, to, kind: "member" });
    }
  }
}

// ---------------------------------------------------------------------------

function main(): void {
  const typesDir = process.argv[2] ?? ".";
  const files = readdirSync(typesDir).filter((f) => f.endsWith(".ts"));
  const rawEdges: Edge[] = [];
  for (const f of files) {
    extractFile(readFileSync(`${typesDir}/${f}`, "utf8"), rawEdges);
  }

  // Dedup edges (the canonicalization collapses helpers -> one node, producing
  // duplicate from/to pairs). Keep one per (from,to); prefer "field" kind label.
  const seen = new Map<string, Edge>();
  for (const e of rawEdges) {
    const key = `${e.from}->${e.to}`;
    if (!seen.has(key)) seen.set(key, e);
  }
  const edges = [...seen.values()].sort((a, b) => (a.from + a.to).localeCompare(b.from + b.to));

  // Degrees.
  const outDeg = new Map<string, number>();
  const inDeg = new Map<string, number>();
  for (const e of edges) {
    outDeg.set(e.from, (outDeg.get(e.from) ?? 0) + 1);
    inDeg.set(e.to, (inDeg.get(e.to) ?? 0) + 1);
  }

  const nodes = Object.entries(NODES)
    .map(([id, meta]) => ({ id, ...meta, inDegree: inDeg.get(id) ?? 0, outDegree: outDeg.get(id) ?? 0 }))
    .sort((a, b) => a.tier - b.tier || a.id.localeCompare(b.id));

  process.stdout.write(JSON.stringify({ level: "type", nodes, edges }, null, 2) + "\n");
}

main();
