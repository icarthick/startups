#!/usr/bin/env node
/**
 * Expected-vs-emitted validation for a telemetry sample run.
 *
 * The runner proves that whatever WAS emitted is well formed. That is only half
 * the question: it says nothing about events that should have been emitted and
 * were not. Missing events are the failure mode that matters here, because the
 * emitter is fail-open by design and a dropped event looks exactly like a phase
 * that never happened.
 *
 * So this script derives the signals a correct implementation MUST deliver and
 * reports which are absent. Three streams per sample:
 *
 *   GROUND TRUTH   the required signal SET, from the final `.phase-status.json`:
 *                  one RUN_STARTED, one PHASE_COMPLETED per resolved phase, one
 *                  terminal (SUCCESS if complete, else ABORTED).
 *   VISIBLE        what the hook could possibly have seen: a diff replay over
 *                  only those writes made with a tool the PostToolUse matcher
 *                  accepts (Write|Edit), recovered from the transcript.
 *   EMITTED        what actually reached the endpoint (events.jsonl).
 *
 * Coverage, not multiplicity. Two earlier models asserted exact counts and both
 * broke: a final-state model scores a legitimate phase re-run as "unexpected",
 * and a write-sequence replay needs every Bash-written JSON blob to be
 * recoverable from the transcript, which it is not. Both reported delivery above
 * 100%, which means the denominator was wrong, not that anything over-delivered.
 * A required signal that is ABSENT is the defect under investigation; the skills
 * genuinely re-run phases, so repeats are reported as information.
 *
 * A missing signal that VISIBLE also lacks is matcher loss (D1a). A missing
 * ABORTED is the session-end path (D1b). Splitting them stops one defect from
 * being mistaken for the other.
 *
 *   validate-events.mjs <logRoot> <scratchRoot> <stateRoot> [transcriptRoot]
 */

import { readFileSync, existsSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";

const [logRoot, scratchRoot, stateRoot, transcriptRootArg] = process.argv.slice(2);
const transcriptRoot = transcriptRootArg ?? join(homedir(), ".claude", "projects");

/**
 * Rebase an absolute path recorded at run time onto the roots given now.
 *
 * The .status files store absolute paths. Analysing an archived run therefore
 * reads whatever currently sits at those original paths — which, if a later run
 * has recreated them, is a different run's data reported under this run's name.
 * That is silent and produced a completely wrong first result, so paths are
 * always rebased rather than trusted.
 */
const rebase = (recorded, root) => {
  if (!recorded || recorded === "none") return recorded;
  const parts = recorded.split("/").filter(Boolean);
  const rootParts = root.split("/").filter(Boolean);
  // Keep the tail that follows the recorded root's own last segment.
  const idx = parts.findIndex((p) => /^\d+-/.test(p));
  if (idx === -1) return recorded;
  return "/" + [...rootParts, ...parts.slice(idx)].join("/");
};

const readJson = (p, d = null) => {
  try {
    return JSON.parse(readFileSync(p, "utf8"));
  } catch {
    return d;
  }
};

// Mirrors emit.mjs. Duplicated rather than imported because emit.mjs exports
// nothing and must stay a single self-contained hook script.
const RESOLVED_STATUS = {
  completed: "SUCCESS",
  skipped: "SKIPPED",
  not_applicable: "NOT_APPLICABLE",
  failed: "FAILED",
};
const PHASES = new Set([
  "DISCOVER", "CLARIFY", "DESIGN", "ESTIMATE", "WORKSHOP", "GENERATE", "FEEDBACK",
]);
const toPhaseEnum = (n) => {
  const u = String(n).toUpperCase();
  return PHASES.has(u) ? u : undefined;
};

/** Faithful replay of emit.mjs diffToEvents. */
const diffToEvents = (previous, current) => {
  const events = [];
  const before = previous?.phases ?? null;
  const after = current.phases ?? {};
  if (before === null) events.push({ eventName: "RUN_STARTED" });
  for (const [name, status] of Object.entries(after)) {
    if (before && before[name] === status) continue;
    const mapped = RESOLVED_STATUS[String(status).toLowerCase()];
    const phase = toPhaseEnum(name);
    if (!mapped || !phase) continue;
    events.push({ eventName: "PHASE_COMPLETED", phase, status: mapped });
  }
  const wasComplete = previous?.current_phase === "complete";
  if (current.current_phase === "complete" && !wasComplete) {
    events.push({
      eventName: "RUN_COMPLETED",
      status: "SUCCESS",
      runMode: current.run_mode === "decide_and_execute" ? "DECIDE_AND_EXECUTE" : "DECIDE",
    });
  }
  return events;
};

/**
 * Comparison key.
 *
 * A terminal event deliberately ignores `phase`. The session-end path stamps
 * RUN_COMPLETED/ABORTED with the phase the run stopped on — which is useful data,
 * not a variant of the event — so keying terminals by phase made a correctly
 * emitted `RUN_COMPLETED/ESTIMATE/ABORTED` fail to match the required
 * `RUN_COMPLETED/ABORTED` and reported a delivered signal as missing.
 */
const key = (e) =>
  e.eventName === "RUN_COMPLETED"
    ? `RUN_COMPLETED/-/${e.status ?? "-"}`
    : `${e.eventName}/${e.phase ?? "-"}/${e.status ?? "-"}`;

/**
 * Recover every write to `.phase-status.json` from a session transcript, in
 * order, tagged with the tool that made it.
 *
 * Bash writes are the whole point of doing this: they are invisible to the hook,
 * so a replay that only understood Write/Edit would silently agree with the
 * emitter and hide the defect. The JSON is recovered from the command text.
 */
const extractWrites = (transcriptPath) => {
  const writes = [];
  if (!existsSync(transcriptPath)) return writes;
  for (const line of readFileSync(transcriptPath, "utf8").split("\n")) {
    let rec;
    try { rec = JSON.parse(line); } catch { continue; }
    const content = rec.message?.content;
    if (!Array.isArray(content)) continue;
    for (const b of content) {
      if (b.type !== "tool_use") continue;
      const blob = JSON.stringify(b.input ?? {});
      if (!blob.includes(".phase-status.json")) continue;

      if (b.name === "Write") {
        const parsed = readJsonString(b.input.content);
        if (parsed?.phases) writes.push({ tool: "Write", state: parsed, visible: true });
        continue;
      }
      if (b.name === "Edit") {
        // Cannot reconstruct without the prior file text; record it so the
        // accounting reports an unknown rather than assuming no change.
        writes.push({ tool: "Edit", state: null, visible: true });
        continue;
      }
      const cmd = b.input.command ?? "";
      // Only count Bash invocations that actually write the file.
      if (!/\.phase-status\.json['"]?\s*,\s*['"]w|open\(['"]\.phase-status|>\s*\.?\/?\.phase-status|tee\s+\.?\/?\.phase-status/.test(cmd)) continue;
      const parsed = findStateObject(cmd);
      writes.push({ tool: b.name, state: parsed, visible: false });
    }
  }
  return writes;
};

const readJsonString = (s) => {
  try { return JSON.parse(s); } catch { return null; }
};

/** Pull the first {...} out of a command that looks like a phase-status body. */
const findStateObject = (text) => {
  for (let i = 0; i < text.length; i++) {
    if (text[i] !== "{") continue;
    let depth = 0;
    for (let j = i; j < text.length; j++) {
      if (text[j] === "{") depth++;
      else if (text[j] === "}") {
        depth--;
        if (depth === 0) {
          const slice = text.slice(i, j + 1);
          if (slice.includes("phases")) {
            const parsed = readJsonString(slice);
            if (parsed?.phases) return parsed;
          }
          i = j;
          break;
        }
      }
    }
  }
  return null;
};

/** Prefer the transcript whose filename IS the run's session id — with repeated
 *  runs in the same scratch dir, "newest" is a guess and the session id is not. */
const findTranscript = (label, sessionId) => {
  const dir = join(transcriptRoot, `-tmp-tel-samples-${label}`);
  if (!existsSync(dir)) return null;
  if (sessionId && sessionId !== "unknown" && existsSync(join(dir, `${sessionId}.jsonl`))) {
    return join(dir, `${sessionId}.jsonl`);
  }
  const files = readdirSync(dir)
    .filter((f) => f.endsWith(".jsonl"))
    .map((f) => join(dir, f))
    .sort((a, b) => statMtime(b) - statMtime(a));
  return files[0] ?? null;
};

const statMtime = (p) => {
  try { return statSync(p).mtimeMs; } catch { return 0; }
};

// ------------------------------------------------------------------ per sample

const statusFiles = existsSync(logRoot)
  ? readdirSync(logRoot).filter((f) => f.endsWith(".status")).sort()
  : [];

let grandExpected = 0, grandEmitted = 0, grandMissing = 0, grandUnexpected = 0;
const rows = [];

for (const sf of statusFiles) {
  const meta = Object.fromEntries(
    readFileSync(join(logRoot, sf), "utf8").trim().split("\n").map((l) => {
      const i = l.indexOf("=");
      return [l.slice(0, i), l.slice(i + 1)];
    }),
  );
  if (!meta.id) continue;
  const label = `${meta.id}-${meta.label}`;
  const state = rebase(meta.state, stateRoot);
  const runDir = meta.run_dir !== "none" ? rebase(meta.run_dir, scratchRoot) : null;

  const evPath = join(state, "events.jsonl");
  const emitted = existsSync(evPath)
    ? readFileSync(evPath, "utf8").trim().split("\n").filter(Boolean).map((l) => JSON.parse(l))
    : [];
  const emittedActs = emitted.map((e) => {
    const ma = e.body?.pluginTelemetryEvent?.migrationActivity ?? {};
    return { ...ma, runMode: ma.attributes?.runMode };
  });

  const finalState = runDir ? readJson(join(runDir, ".phase-status.json")) : null;

  const writes = extractWrites(findTranscript(label, meta.session_id));
  let unparsedEdits = writes.filter((w) => !w.state).length;

  /**
   * Replay the diff over a sequence of writes, grouped by `migration_id`.
   *
   * Grouping matters: a session can create more than one `.migration/<id>/` dir,
   * each with its own snapshot, so a single global replay would diff one run's
   * state against another's and invent transitions.
   */
  const replay = (selected) => {
    const events = [];
    const prevByRun = new Map();
    for (const w of selected) {
      if (!w.state) continue;
      const id = w.state.migration_id ?? "__unkeyed__";
      for (const e of diffToEvents(prevByRun.get(id) ?? null, w.state)) events.push(e);
      prevByRun.set(id, w.state);
    }
    return events;
  };

  // GROUND TRUTH: the set of signals that MUST appear at least once.
  //
  // Multiplicity is deliberately not asserted. Two earlier models both failed on
  // it: deriving expected events from the final on-disk state scores a legitimate
  // phase re-run as "unexpected", and replaying the write sequence needs every
  // Bash-written JSON blob to be recoverable from the transcript, which it is not.
  // Both produced delivery rates above 100%, which says the denominator was wrong
  // rather than that anything over-delivered.
  //
  // What actually matters for this validation is whether a required signal is
  // ABSENT — a dropped event is the failure mode under investigation, and the
  // skills legitimately re-run phases, so repeats are reported separately as
  // information rather than counted as defects.
  const truth = [];
  if (finalState) {
    truth.push({ eventName: "RUN_STARTED" });
    for (const [name, status] of Object.entries(finalState.phases ?? {})) {
      const mapped = RESOLVED_STATUS[String(status).toLowerCase()];
      const phase = toPhaseEnum(name);
      if (mapped && phase) truth.push({ eventName: "PHASE_COMPLETED", phase, status: mapped });
    }
    truth.push(finalState.current_phase === "complete"
      ? { eventName: "RUN_COMPLETED", status: "SUCCESS" }
      : { eventName: "RUN_COMPLETED", status: "ABORTED" });
  }

  // VISIBLE: replay over Write/Edit writes only.
  const visible = replay(writes.filter((w) => w.visible));

  // Multiset comparison.
  const tally = (list) => {
    const m = new Map();
    for (const e of list) m.set(key(e), (m.get(key(e)) ?? 0) + 1);
    return m;
  };
  const tTruth = tally(truth), tEmit = tally(emittedActs), tVis = tally(visible);

  const allKeys = [...new Set([...tTruth.keys(), ...tEmit.keys(), ...tVis.keys()])].sort();
  const missing = [], unexpected = [];

  console.log("=".repeat(96));
  console.log(`SAMPLE ${meta.id} ${meta.label}   (${meta.rel})`);
  console.log(`  final disk state: current_phase=${finalState?.current_phase ?? "?"} ` +
    `phases=${JSON.stringify(finalState?.phases ?? {})}`);
  console.log(`  phase-status writes: ${writes.length} total ` +
    `(${writes.filter((w) => w.visible).length} via Write/Edit, ` +
    `${writes.filter((w) => !w.visible).length} via Bash — Bash is invisible to the matcher)` +
    (unparsedEdits ? `  [${unparsedEdits} Edit write(s) not reconstructible]` : ""));
  console.log(`  forced_session_end=${meta.forced_session_end ?? "?"}`);
  console.log("");
  console.log(`  ${"event".padEnd(42)} ${"truth".padStart(5)} ${"visible".padStart(7)} ${"emitted".padStart(7)}   verdict`);
  for (const k of allKeys) {
    const t = tTruth.get(k) ?? 0, v = tVis.get(k) ?? 0, e = tEmit.get(k) ?? 0;
    const isAborted = k.startsWith("RUN_COMPLETED") && k.endsWith("/ABORTED");
    let verdict;
    if (t > 0 && e === 0) {
      // Required signal absent — the defect this validation exists to find.
      // An ABORTED terminal can only come from the session-end path, which
      // diffToEvents never produces, so `visible` is structurally 0 for it and
      // must not be read as matcher loss.
      if (isAborted) verdict = "MISSING — SessionEnd hook never runs (D1b)";
      else if (v === 0) verdict = "MISSING — transition written by Bash, invisible to matcher (D1a)";
      else verdict = "MISSING — hook saw the write but no event arrived (async teardown / snapshot race)";
      missing.push({ k, n: 1 });
    } else if (t > 0) {
      verdict = e > t ? `OK (+${e - t} repeat, phase re-ran)` : "OK";
      if (e > t) unexpected.push({ k, n: e - t });
    } else {
      // Not required by final state, but emitted: a phase that completed and was
      // later reset (the workshop does this). Real, not a defect.
      verdict = `repeat/reset x${e} — completed then reset in final state`;
      unexpected.push({ k, n: e });
    }
    console.log(`  ${k.padEnd(42)} ${String(t).padStart(5)} ${String(v).padStart(7)} ${String(e).padStart(7)}   ${verdict}`);
  }

  // ---- trigger accounting
  //
  // Event counts alone cannot tell a hook that ran and correctly found no delta
  // from a hook that never ran. Those need opposite fixes, so triggers are
  // counted separately and reconciled against the endpoint.
  const tracePath = join(state, "trace.jsonl");
  const traces = existsSync(tracePath)
    ? readFileSync(tracePath, "utf8").trim().split("\n").filter(Boolean).map((l) => JSON.parse(l))
    : [];
  if (traces.length) {
    const byMode = new Map();
    for (const t of traces) {
      const m = byMode.get(t.mode) ?? { n: 0, posted: 0, outcomes: new Map() };
      m.n++;
      m.posted += t.posted ?? 0;
      m.outcomes.set(t.outcome, (m.outcomes.get(t.outcome) ?? 0) + 1);
      byMode.set(t.mode, m);
    }
    console.log("");
    console.log("  TRIGGERS (hook process launches)");
    console.log(`    ${"mode".padEnd(18)} ${"fired".padStart(5)} ${"posted".padStart(6)}   outcomes`);
    for (const [mode, m] of byMode) {
      const outs = [...m.outcomes.entries()].map(([k, v]) => `${k}=${v}`).join(" ");
      console.log(`    ${mode.padEnd(18)} ${String(m.n).padStart(5)} ${String(m.posted).padStart(6)}   ${outs}`);
    }
    const fired = traces.length;
    const productive = traces.filter((t) => (t.posted ?? 0) > 0).length;
    const postedTotal = traces.reduce((a, t) => a + (t.posted ?? 0), 0);
    console.log(`    TOTAL              ${String(fired).padStart(5)} ${String(postedTotal).padStart(6)}   ` +
      `${productive}/${fired} invocations reached the endpoint (${((productive / fired) * 100).toFixed(0)}%)`);
    // Cross-check the trace against the two independent records of the same
    // facts. Read the harness log here rather than reusing the copy taken later
    // in this loop — that one is declared further down and would be in its
    // temporal dead zone.
    const hlog = join(scratchRoot, `${meta.id}-${meta.label}`, `harness-${meta.port}.log`);
    const hText = existsSync(hlog) ? readFileSync(hlog, "utf8") : "";
    const harnessPosts = Math.max(0, (hText.match(/POST \/v1\/plugin-telemetry-event/g) ?? []).length - 1); // minus liveness probe
    console.log(`    cross-check: trace posted=${postedTotal}  events.jsonl=${emitted.length}  harness POSTs=${harnessPosts}` +
      `  ${postedTotal === emitted.length && emitted.length === harnessPosts ? "AGREE" : "*** MISMATCH ***"}`);
  } else {
    console.log("\n  TRIGGERS: no trace.jsonl — hook never launched, or DEBUG was off");
  }

  const expN = truth.length, emitN = emittedActs.length;
  const missN = missing.length;
  const unexpN = unexpected.reduce((a, b) => a + b.n, 0);
  console.log("");
  console.log(`  required signals ${expN}, delivered ${expN - missN}, MISSING ${missN}, repeats ${unexpN}, total events ${emitN}` +
    `  => ${missN === 0 ? "COMPLETE" : "INCOMPLETE"}`);

  grandExpected += expN; grandEmitted += emitN; grandMissing += missN; grandUnexpected += unexpN;
  rows.push({
    sample: `${meta.id} ${meta.label}`,
    required: expN, delivered: expN - missN, missing: missN, repeats: unexpN, events: emitN,
    bashWrites: writes.filter((w) => !w.visible).length,
    complete: missN === 0 ? "y" : "n",
  });
}

console.log("\n" + "=".repeat(96));
console.log("EXPECTED-VS-EMITTED ACCOUNTING\n");
const cols = ["sample", "required", "delivered", "missing", "repeats", "events", "bashWrites", "complete"];
const w = cols.map((c) => Math.max(c.length, ...rows.map((r) => String(r[c]).length)));
console.log(cols.map((c, i) => c.padEnd(w[i])).join("  "));
console.log(w.map((n) => "-".repeat(n)).join("  "));
for (const r of rows) console.log(cols.map((c, i) => String(r[c]).padEnd(w[i])).join("  "));
console.log("");
console.log(`TOTAL required ${grandExpected}, delivered ${grandExpected - grandMissing}, MISSING ${grandMissing}, repeats ${grandUnexpected}, events emitted ${grandEmitted}`);
console.log(`Delivery rate: ${grandExpected ? (((grandExpected - grandMissing) / grandExpected) * 100).toFixed(1) : "n/a"}% of required signals reached the endpoint`);
