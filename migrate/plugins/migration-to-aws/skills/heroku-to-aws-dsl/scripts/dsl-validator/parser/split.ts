// scripts/dsl-validator/parser/split.ts
//
// Body splitter — pure structural decomposition of a whole unit file into the
// regions of the "Unit file regions" grammar: frontmatter -> H1 -> optional
// Orientation -> zero-or-more Step sections -> (trailing, which should be empty).
//
// One job: split into named raw regions. No YAML parse, no binding. The body-side
// analogue of parseYaml. frontmatter text feeds bindFrontmatter; each step body
// feeds bindStep; orientation feeds bindOrientation.
//
// Error model: THROWS only on the one truly-malformed case (no frontmatter fence
// — not a unit file). Everything else (missing H1, trailing content) is captured
// and left for the check layer to flag as Findings.

export class SplitError extends Error {
  readonly line: number;
  constructor(message: string, line: number) {
    super(`unit split error (line ${line}): ${message}`);
    this.name = "SplitError";
    this.line = line;
  }
}

export interface StepSection {
  /** From the `## Step: <id>` heading. */
  readonly id: string;
  /** The raw section body (```meta``` fence + prose), verbatim. */
  readonly body: string;
  /** 1-based line of the `## Step:` heading. */
  readonly line: number;
}

export interface SplitUnit {
  /** Text between the first `---` ... `---` fences (raw, for parseYaml). */
  readonly frontmatterText: string;
  /** The H1 title text, if present. */
  readonly title?: string;
  /** The `## Orientation` prose body, if present. */
  readonly orientation?: string;
  /** Each `## Step: <id>` section, in order. */
  readonly steps: readonly StepSection[];
  /** Anything after the last step / orientation (should be empty — a REGIONS check). */
  readonly trailing?: string;
}

const FRONTMATTER_RE = /^---\n([\s\S]*?)\n---\n?/;

export function splitUnitFile(text: string): SplitUnit {
  const fm = text.match(FRONTMATTER_RE);
  if (!fm) throw new SplitError("no frontmatter fence (`---` ... `---`)", 1);
  const frontmatterText = fm[1];

  // The body is everything after the frontmatter fence.
  const bodyStart = fm[0].length;
  const body = text.slice(bodyStart);
  const fmLineCount = text.slice(0, bodyStart).split("\n").length - 1; // lines consumed by frontmatter

  const lines = body.split("\n");
  // line numbers in the ORIGINAL file = fmLineCount + (index within body) + 1
  const origLine = (bodyIdx: number): number => fmLineCount + bodyIdx + 1;

  let title: string | undefined;
  let orientation: string | undefined;
  const steps: StepSection[] = [];

  // Walk top-level headings. A region accumulates lines until the next heading.
  type Region = { kind: "h1" | "orientation" | "step" | "pre"; id?: string; startIdx: number; lines: string[] };
  const regions: Region[] = [];
  let current: Region = { kind: "pre", startIdx: 0, lines: [] };

  lines.forEach((ln, i) => {
    const h1 = ln.match(/^#\s+(.*)$/);
    const orient = ln.match(/^##\s+Orientation\s*$/);
    const step = ln.match(/^##\s+Step:\s*(\S+)\s*$/);
    if (h1) {
      regions.push(current);
      current = { kind: "h1", startIdx: i, lines: [] };
      title = h1[1].trim();
    } else if (orient) {
      regions.push(current);
      current = { kind: "orientation", startIdx: i, lines: [] };
    } else if (step) {
      regions.push(current);
      current = { kind: "step", id: step[1], startIdx: i, lines: [] };
    } else {
      current.lines.push(ln);
    }
  });
  regions.push(current);

  // Assemble named regions in order. Track trailing = content after the last
  // step/orientation that isn't part of a recognized region body.
  let sawStepOrOrientation = false;
  const trailingChunks: string[] = [];

  for (const r of regions) {
    const content = r.lines.join("\n").trim();
    if (r.kind === "orientation") {
      orientation = content;
      sawStepOrOrientation = true;
    } else if (r.kind === "step") {
      steps.push({ id: r.id!, body: content, line: origLine(r.startIdx) });
      sawStepOrOrientation = true;
    }
    // h1 / pre region bodies: any non-empty prose here that is NOT a recognized
    // region is trailing-ish only AFTER we've seen steps/orientation. Before that,
    // the h1's own trailing lines belong to nothing normative; capture as trailing
    // only if non-empty and positioned after content regions.
  }

  // Trailing = anything in the LAST region if it is an h1/pre AFTER steps exist,
  // OR non-empty content following the final step within step bodies is already
  // captured in that step. The simplest faithful rule: if the final region is an
  // h1/pre with non-empty content and steps/orientation preceded it, it's trailing.
  const last = regions[regions.length - 1];
  if (sawStepOrOrientation && (last.kind === "h1" || last.kind === "pre")) {
    const c = last.lines.join("\n").trim();
    if (c !== "") trailingChunks.push(c);
  }
  const trailing = trailingChunks.length > 0 ? trailingChunks.join("\n") : undefined;

  return {
    frontmatterText,
    ...(title !== undefined ? { title } : {}),
    ...(orientation !== undefined ? { orientation } : {}),
    steps,
    ...(trailing !== undefined ? { trailing } : {}),
  };
}
