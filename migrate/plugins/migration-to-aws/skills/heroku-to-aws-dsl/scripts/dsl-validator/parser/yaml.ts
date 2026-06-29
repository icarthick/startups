// scripts/dsl-validator/parser/yaml.ts
//
// YAML-subset reader — pure SYNTAX layer. text -> YamlValue. Knows NOTHING about
// the DSL. Parses only the constrained subset catalogued in dsl-types.md
// ("The YAML subset"): comments, scalars (bare/quoted/null/bool), folded block
// scalars (>), block sequences (-), block maps (indentation), inline flow maps
// ({}), inline flow sequences ([]).
//
// Error model: this layer THROWS YamlParseError on malformed input (a document
// either parses or it doesn't). The semantic/binder layer accumulates Findings.

/** A parsed YAML value tree. Numbers are kept as strings (see dsl-types.md). */
export type YamlValue =
  | string
  | boolean
  | null
  | readonly YamlValue[]
  | { readonly [k: string]: YamlValue };

/** Thrown on malformed YAML-subset input. Carries 1-based line context. */
export class YamlParseError extends Error {
  readonly line: number;
  constructor(message: string, line: number) {
    super(`YAML parse error (line ${line}): ${message}`);
    this.name = "YamlParseError";
    this.line = line;
  }
}

/** A source line carried with its original 1-based number (for error context). */
interface Line {
  readonly n: number;
  readonly text: string;
}

// ---------------------------------------------------------------------------
// Public entry
// ---------------------------------------------------------------------------

/**
 * Parse a YAML-subset document into a YamlValue tree.
 * @throws YamlParseError on malformed input.
 */
export function parseYaml(text: string): YamlValue {
  const lines = stripComments(text);
  if (lines.length === 0) return {};
  return parseBlock(lines, indentOf(lines[0].text));
}

// ---------------------------------------------------------------------------
// One-job private helpers
// ---------------------------------------------------------------------------

const indentOf = (s: string): number => s.length - s.trimStart().length;
const isBlank = (s: string): boolean => s.trim() === "";

/** Drop full-line `#` comments and blank lines. Preserves original line numbers. */
function stripComments(text: string): Line[] {
  const out: Line[] = [];
  text.split("\n").forEach((raw, i) => {
    const t = raw.replace(/\s+$/, ""); // trailing whitespace
    const trimmed = t.trimStart();
    if (trimmed.startsWith("#")) return; // full-line comment
    if (isBlank(t)) return; // blank
    out.push({ n: i + 1, text: t });
  });
  return out;
}

/**
 * The recursive indentation-driven core. All lines passed in belong to ONE block
 * at the given `indent`. Decide map vs sequence vs scalar and parse.
 */
function parseBlock(lines: Line[], indent: number): YamlValue {
  if (lines.length === 0) return {};
  const first = lines[0];
  const firstTrim = first.text.trimStart();

  // Block sequence: every top-indent line at `indent` starts with "- ".
  if (firstTrim.startsWith("- ") || firstTrim === "-") {
    return parseSequence(lines, indent);
  }
  // Otherwise a block map (key: ...).
  return parseMap(lines, indent);
}

/** Group the lines into entries at `indent`; each entry is a head line + its deeper children. */
function entriesAt(lines: Line[], indent: number): { head: Line; children: Line[] }[] {
  const groups: { head: Line; children: Line[] }[] = [];
  for (let i = 0; i < lines.length; i++) {
    const ind = indentOf(lines[i].text);
    if (ind < indent) {
      throw new YamlParseError(`unexpected dedent (expected indent >= ${indent})`, lines[i].n);
    }
    if (ind === indent) {
      groups.push({ head: lines[i], children: [] });
    } else {
      if (groups.length === 0) throw new YamlParseError("indented line without a parent", lines[i].n);
      groups[groups.length - 1].children.push(lines[i]);
    }
  }
  return groups;
}

function parseMap(lines: Line[], indent: number): YamlValue {
  const obj: { [k: string]: YamlValue } = {};
  for (const { head, children } of entriesAt(lines, indent)) {
    const t = head.text.trim();
    const ci = colonSplit(t, head.n);
    const key = ci.key;
    const inline = ci.rest;

    if (inline === "") {
      // value lives in children (nested map/sequence) — or empty
      obj[key] = children.length > 0 ? parseBlock(children, indentOf(children[0].text)) : "";
    } else if (inline === ">" || inline === "|") {
      obj[key] = parseBlockScalar(children, indent);
    } else {
      // scalar / flow on the same line; children (if any) are invalid here
      if (children.length > 0) {
        throw new YamlParseError(`key "${key}" has both an inline value and a nested block`, children[0].n);
      }
      obj[key] = parseValue(inline, head.n);
    }
  }
  return obj;
}

function parseSequence(lines: Line[], indent: number): YamlValue {
  const arr: YamlValue[] = [];
  for (const { head, children } of entriesAt(lines, indent)) {
    const t = head.text.trim();
    if (t !== "-" && !t.startsWith("- ")) {
      throw new YamlParseError(`expected sequence item ("- ...")`, head.n);
    }
    const item = t === "-" ? "" : t.slice(2).trim();

    if (item === "") {
      arr.push(children.length > 0 ? parseBlock(children, indentOf(children[0].text)) : "");
      continue;
    }
    // A sequence item may itself be a "key: value" (possibly a multi-key map whose
    // sibling keys + nested blocks live in `children`) or a scalar/flow value.
    if (isFlow(item)) {
      arr.push(parseFlow(item, head.n));
    } else if (looksLikeMapEntry(item)) {
      // The item-map begins at the column of `key` (just past "- "). Rebuild a
      // synthetic head line at that real indent, then parse head + children as a
      // map at that indent so sibling keys + nested blocks attribute correctly.
      const headIndent = indentOf(head.text);
      const keyCol = headIndent + (head.text.trimStart().length - item.length);
      const pad = " ".repeat(keyCol);
      const synthetic: Line[] = [{ n: head.n, text: pad + item }, ...children];
      arr.push(parseMap(synthetic, keyCol));
    } else {
      if (children.length > 0) {
        throw new YamlParseError(`scalar sequence item cannot have a nested block`, children[0].n);
      }
      arr.push(parseValue(item, head.n));
    }
  }
  return arr;
}

/** A scalar-or-flow value on the RHS of a `key:` or after a `- `. */
function parseValue(str: string, line: number): YamlValue {
  const s = str.trim();
  if (isFlow(s)) return parseFlow(s, line);
  return parseScalar(s);
}

const isFlow = (s: string): boolean => s.startsWith("{") || s.startsWith("[");
const looksLikeMapEntry = (s: string): boolean => /^[^\s:{}[\]]+:/.test(s) || /^_[a-z_]+:/.test(s);

/** Parse an inline flow construct (`{...}` map or `[...]` sequence), recursively. */
function parseFlow(str: string, line: number): YamlValue {
  const s = str.trim();
  if (s.startsWith("[")) {
    const inner = expectWrapped(s, "[", "]", line);
    if (inner.trim() === "") return [];
    return splitTopLevel(inner, line).map((part) => parseValue(part, line));
  }
  if (s.startsWith("{")) {
    const inner = expectWrapped(s, "{", "}", line);
    const obj: { [k: string]: YamlValue } = {};
    if (inner.trim() === "") return obj;
    for (const part of splitTopLevel(inner, line)) {
      const { key, rest } = colonSplit(part.trim(), line);
      obj[key] = parseValue(rest, line);
    }
    return obj;
  }
  throw new YamlParseError(`not a flow construct: ${s}`, line);
}

/** Parse a single scalar token: quoted string, null, true/false, or bare token. */
function parseScalar(str: string): YamlValue {
  const s = str.trim();
  if (s.length >= 2 && ((s[0] === '"' && s.endsWith('"')) || (s[0] === "'" && s.endsWith("'")))) {
    return s.slice(1, -1);
  }
  if (s === "null" || s === "~") return null;
  if (s === "true") return true;
  if (s === "false") return false;
  return s; // bare token (incl. numbers-as-strings)
}

/** Parse a folded block scalar (`>`): join the indented continuation lines with spaces. */
function parseBlockScalar(children: Line[], parentIndent: number): string {
  if (children.length === 0) return "";
  return children.map((c) => c.text.trim()).join(" ").trim();
}

// ---------------------------------------------------------------------------
// small string utilities
// ---------------------------------------------------------------------------

/** Split "key: rest" at the FIRST top-level colon. Returns trimmed key + raw rest. */
function colonSplit(s: string, line: number): { key: string; rest: string } {
  // find first ": " or trailing ":" not inside quotes/brackets
  let depth = 0, q: string | null = null;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (q) {
      if (c === q) q = null;
      continue;
    }
    if (c === '"' || c === "'") q = c;
    else if (c === "{" || c === "[") depth++;
    else if (c === "}" || c === "]") depth--;
    else if (c === ":" && depth === 0 && (i + 1 >= s.length || s[i + 1] === " ")) {
      return { key: stripQuotes(s.slice(0, i).trim()), rest: s.slice(i + 1).trim() };
    }
  }
  throw new YamlParseError(`expected "key: value", got: ${s}`, line);
}

const stripQuotes = (s: string): string =>
  s.length >= 2 && ((s[0] === '"' && s.endsWith('"')) || (s[0] === "'" && s.endsWith("'"))) ? s.slice(1, -1) : s;

function expectWrapped(s: string, open: string, close: string, line: number): string {
  if (!s.startsWith(open) || !s.endsWith(close)) {
    throw new YamlParseError(`unbalanced ${open}${close}: ${s}`, line);
  }
  return s.slice(1, -1);
}

/** Split a flow body on top-level commas (ignoring commas inside nested {} [] ""). */
function splitTopLevel(s: string, line: number): string[] {
  const parts: string[] = [];
  let depth = 0, q: string | null = null, start = 0;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (q) {
      if (c === q) q = null;
      continue;
    }
    if (c === '"' || c === "'") q = c;
    else if (c === "{" || c === "[") depth++;
    else if (c === "}" || c === "]") depth--;
    else if (c === "," && depth === 0) {
      parts.push(s.slice(start, i));
      start = i + 1;
    }
  }
  if (depth !== 0) throw new YamlParseError(`unbalanced brackets in flow: ${s}`, line);
  parts.push(s.slice(start));
  return parts.map((p) => p.trim()).filter((p) => p !== "");
}
