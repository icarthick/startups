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
 * Coverage is scored as a SET comparison, not a count. Two earlier models
 * asserted exact counts and both broke: a final-state model scores a legitimate
 * phase re-run as "unexpected", and a write-sequence replay needs every
 * Bash-written JSON blob to be recoverable from the transcript, which it is not.
 * Both reported delivery above 100%, which means the denominator was wrong, not
 * that anything over-delivered. A required signal that is ABSENT is the defect
 * that comparison exists to find.
 *
 * A missing signal that VISIBLE also lacks is matcher loss (D1a). A missing
 * ABORTED is the session-end path (D1b). Splitting them stops one defect from
 * being mistaken for the other.
 *
 * MULTIPLICITY is then checked separately, because set coverage is blind to a
 * signal arriving twice and that blindness let two duplicate-run defects survive
 * seven otherwise-clean matrix runs. Rather than reinstate an exact-count model
 * that cannot tell a re-run from a duplicate, the checks are restricted to shapes
 * no legitimate run can produce — chiefly more than one runId per run directory —
 * and everything a re-run could explain is printed as information. Those checks
 * are the only part of this script that sets a non-zero exit status.
 *
 *   validate-events.mjs <logRoot> <scratchRoot> <stateRoot> [transcriptRoot]
 *
 *   DUP_WINDOW_MS   how close two identical signals must be to count as a
 *                   duplicate rather than a re-run (default 2000)
 */

import { readFileSync, existsSync, readdirSync, statSync } from "node:fs";
import { join, dirname } from "node:path";
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

/**
 * The host's transcript directory for a sample: the working directory the run
 * actually used, with every `/` replaced by `-`.
 *
 * Taken from the `scratch=` line the runner recorded, NOT from the scratch root
 * passed to this script. Those differ in both directions and each was wrong once:
 * the path was hardcoded to `/tmp/tel-samples`, so running the matrix anywhere
 * else silently found no transcript and reported every sample as matcher loss;
 * and deriving it from the rebased root instead breaks the archive case, where
 * the run happened in `/tmp` and only its outputs were moved. The transcript
 * lives wherever the host put it at run time, so the recorded path is the only
 * one that is right in both cases.
 */
const transcriptDirFor = (recordedScratch) =>
  join(transcriptRoot, String(recordedScratch).replace(/\//g, "-"));

/** Prefer the transcript whose filename IS the run's session id — with repeated
 *  runs in the same scratch dir, "newest" is a guess and the session id is not. */
const findTranscript = (recordedScratch, sessionId) => {
  const dir = transcriptDirFor(recordedScratch);
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

let grandExpected = 0, grandEmitted = 0, grandMissing = 0, grandUnexpected = 0, grandDefects = 0;
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

  // The envelope fields the multiplicity checks below need: which run an event
  // claims, its dedup key, and when it was stamped. Kept separate from
  // `emittedActs` so the coverage comparison keeps comparing exactly what it did.
  const emittedFull = emitted.map((e) => {
    const ma = e.body?.pluginTelemetryEvent?.migrationActivity ?? {};
    return {
      runId: ma.runId,
      eventId: e.body?.eventId,
      occurredAt: e.body?.occurredAt,
      key: key({ ...ma, runMode: ma.attributes?.runMode }),
      eventName: ma.eventName,
    };
  });

  const finalState = runDir ? readJson(join(runDir, ".phase-status.json")) : null;

  const writes = extractWrites(findTranscript(meta.scratch, meta.session_id));
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
  // Multiplicity is deliberately not asserted HERE. Two earlier models both failed
  // on it: deriving expected events from the final on-disk state scores a
  // legitimate phase re-run as "unexpected", and replaying the write sequence needs
  // every Bash-written JSON blob to be recoverable from the transcript, which it is
  // not. Both produced delivery rates above 100%, which says the denominator was
  // wrong rather than that anything over-delivered.
  //
  // What this comparison answers is whether a required signal is ABSENT — a dropped
  // event is a failure mode under investigation, and the skills legitimately re-run
  // phases, so repeats are reported separately as information rather than counted
  // as defects. Duplication is checked further down, against invariants that do not
  // need the write history to be recoverable.
  const truth = [];
  if (finalState) {
    truth.push({ eventName: "RUN_STARTED" });
    for (const [name, status] of Object.entries(finalState.phases ?? {})) {
      const mapped = RESOLVED_STATUS[String(status).toLowerCase()];
      const phase = toPhaseEnum(name);
      if (mapped && phase) truth.push({ eventName: "PHASE_COMPLETED", phase, status: mapped });
    }
    // A terminal is required only from a run that actually finished.
    //
    // This used to require RUN_COMPLETED/ABORTED from an unfinished one, which
    // asserts behaviour the design deliberately removed: abandonment is a claim
    // about the future, session end cannot observe the future, and emitting
    // ABORTED there produced two terminals for one run whenever a customer
    // resumed. An unfinished run is IN FLIGHT, which is a legitimate third state
    // and not a missing event. Every sample in the previous baseline happened to
    // finish, so the stale expectation cost nothing and stayed invisible.
    if (finalState.current_phase === "complete") {
      truth.push({ eventName: "RUN_COMPLETED", status: "SUCCESS" });
    }
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
    let verdict;
    if (t > 0 && e === 0) {
      // Required signal absent — the defect this validation exists to find.
      if (v === 0) verdict = "MISSING — transition written by Bash, invisible to matcher (D1a)";
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

  // ---- multiplicity
  //
  // Everything above this point measures coverage: whether each required signal
  // arrived at least once. That is deliberately blind to a signal arriving twice,
  // which is why two duplicate-run defects survived seven clean matrix runs — an
  // unserialised snapshot read-modify-write reporting one migration as two runs,
  // and an unreadable snapshot re-emitting a whole history under a fresh runId.
  // Both are invisible to a set comparison and obvious to a count.
  //
  // These checks are chosen to be SOUND rather than complete: the skills
  // legitimately re-run phases, so anything a re-run can explain is reported as
  // information, and only the shapes no legitimate run can produce are called
  // defects. A false alarm here would be worse than the gap it closes, because
  // the next person would learn to ignore the section.
  const defects = [];
  const notes = [];

  // Every `.migration/<id>/` with a phase file is one run, and the snapshot beside
  // it holds the runId that run was reported under. That mapping is what makes
  // "more runIds than runs" decidable.
  const migrationRoot = runDir ? dirname(runDir) : null;
  const runDirs = migrationRoot && existsSync(migrationRoot)
    ? readdirSync(migrationRoot)
        .map((e) => join(migrationRoot, e))
        .filter((d) => existsSync(join(d, ".phase-status.json")))
    : [];
  const snapshotRunIds = new Set(
    runDirs.map((d) => readJson(join(d, ".telemetry-snapshot.json"))?.runId).filter(Boolean),
  );

  const byRun = new Map();
  for (const e of emittedFull) {
    const list = byRun.get(e.runId) ?? [];
    list.push(e);
    byRun.set(e.runId, list);
  }

  // D-M1: one runId per run directory.
  //
  // The runId is minted once and then read back from that run's own snapshot, so
  // there is no legitimate path from one `.migration/<id>/` to two runIds. More
  // runIds than run directories is the duplicate-run signature directly, and it
  // inflates the one number this system exists to produce.
  if (runDirs.length && byRun.size > runDirs.length) {
    defects.push(
      `${byRun.size} distinct runId(s) for ${runDirs.length} run director${runDirs.length === 1 ? "y" : "ies"} ` +
      `— one migration reported as several runs`,
    );
  }

  // D-M2: no runId that no snapshot claims.
  //
  // The losing half of a duplicated run leaves exactly this trace: events under a
  // runId that the surviving snapshot does not hold, so the run never completes
  // and sits in the funnel as a permanent drop-off.
  if (snapshotRunIds.size) {
    const orphans = [...byRun.keys()].filter((r) => r && !snapshotRunIds.has(r));
    if (orphans.length) {
      defects.push(
        `orphan runId(s) held by no snapshot: ${orphans.join(", ")} ` +
        `— events attributed to a run nothing can complete`,
      );
    }
  }

  for (const [runId, evs] of byRun) {
    const short = String(runId).slice(0, 8);

    // D-M3: exactly one RUN_STARTED per runId. Two means the snapshot was lost
    // while the runId survived, which cannot happen — they live in the same file.
    const starts = evs.filter((e) => e.eventName === "RUN_STARTED").length;
    if (starts > 1) defects.push(`runId ${short}: ${starts} RUN_STARTED (want exactly 1)`);

    // D-M4: at most one terminal per runId. The rubric requires exactly one, and
    // two was the observed shape of the withdrawn client-side ABORTED.
    const terminals = evs.filter((e) => e.eventName === "RUN_COMPLETED").length;
    if (terminals > 1) defects.push(`runId ${short}: ${terminals} terminal events (want at most 1)`);
  }

  // D-M5: eventId is the downstream dedup key, so a repeat means one occurrence
  // cannot be told from two no matter what the lake does.
  const idCounts = new Map();
  for (const e of emittedFull) idCounts.set(e.eventId, (idCounts.get(e.eventId) ?? 0) + 1);
  const dupIds = [...idCounts.entries()].filter(([id, n]) => id && n > 1);
  if (dupIds.length) {
    defects.push(`repeated eventId(s): ${dupIds.map(([id, n]) => `${String(id).slice(0, 8)}x${n}`).join(", ")}`);
  }

  // D-M6: the same signal twice within a window no agent turn can fit inside.
  //
  // This is the check that separates a duplicate from a re-run without needing the
  // write history, which is not fully recoverable. A phase genuinely re-running has
  // to leave its resolved status and come back, which takes agent turns; two
  // identical signals milliseconds apart are two processes reporting the same
  // transition. Set DUP_WINDOW_MS to widen it.
  const DUP_WINDOW_MS = Number(process.env.DUP_WINDOW_MS ?? 2000);
  const seenAt = new Map();
  for (const e of emittedFull) {
    const k = `${e.runId}|${e.key}`;
    const prior = seenAt.get(k);
    if (prior != null && typeof e.occurredAt === "number" && Math.abs(e.occurredAt - prior) <= DUP_WINDOW_MS) {
      defects.push(
        `runId ${String(e.runId).slice(0, 8)}: ${e.key} emitted twice within ` +
        `${Math.abs(e.occurredAt - prior)}ms — too close to be a phase re-run`,
      );
    }
    if (typeof e.occurredAt === "number") seenAt.set(k, e.occurredAt);
  }

  // Repeats outside that window: real, and the skills do re-run phases, so these
  // are reported so the count is visible rather than asserted on.
  const repeatKeys = new Map();
  for (const e of emittedFull) {
    const k = `${String(e.runId).slice(0, 8)}|${e.key}`;
    repeatKeys.set(k, (repeatKeys.get(k) ?? 0) + 1);
  }
  for (const [k, n] of repeatKeys) if (n > 1) notes.push(`${k} x${n}`);

  console.log("");
  console.log(`  MULTIPLICITY (${runDirs.length} run dir(s), ${byRun.size} runId(s), ` +
    `${emittedFull.length} event(s))`);
  if (!emittedFull.length) {
    console.log("    no events — nothing to count");
  } else {
    for (const d of defects) console.log(`    *** DEFECT: ${d}`);
    for (const n of notes) console.log(`    repeat (legitimate re-run unless paired with a defect): ${n}`);
    if (!defects.length) console.log("    OK — one runId per run, one RUN_STARTED each, no repeated eventId");
  }
  grandDefects += defects.length;

  const expN = truth.length, emitN = emittedActs.length;
  const missN = missing.length;
  const unexpN = unexpected.reduce((a, b) => a + b.n, 0);
  console.log("");
  console.log(`  required signals ${expN}, delivered ${expN - missN}, MISSING ${missN}, repeats ${unexpN}, total events ${emitN}` +
    `  => ${missN === 0 ? "COMPLETE" : "INCOMPLETE"}` +
    `${defects.length ? `, ${defects.length} MULTIPLICITY DEFECT(S)` : ""}`);

  grandExpected += expN; grandEmitted += emitN; grandMissing += missN; grandUnexpected += unexpN;
  rows.push({
    sample: `${meta.id} ${meta.label}`,
    required: expN, delivered: expN - missN, missing: missN, repeats: unexpN, events: emitN,
    runIds: byRun.size, dupDefects: defects.length,
    bashWrites: writes.filter((w) => !w.visible).length,
    complete: missN === 0 ? "y" : "n",
  });
}

console.log("\n" + "=".repeat(96));
console.log("EXPECTED-VS-EMITTED ACCOUNTING\n");
const cols = ["sample", "required", "delivered", "missing", "repeats", "events", "runIds", "dupDefects", "bashWrites", "complete"];
const w = cols.map((c) => Math.max(c.length, ...rows.map((r) => String(r[c]).length)));
console.log(cols.map((c, i) => c.padEnd(w[i])).join("  "));
console.log(w.map((n) => "-".repeat(n)).join("  "));
for (const r of rows) console.log(cols.map((c, i) => String(r[c]).padEnd(w[i])).join("  "));
console.log("");
console.log(`TOTAL required ${grandExpected}, delivered ${grandExpected - grandMissing}, MISSING ${grandMissing}, repeats ${grandUnexpected}, events emitted ${grandEmitted}`);
console.log(`Delivery rate: ${grandExpected ? (((grandExpected - grandMissing) / grandExpected) * 100).toFixed(1) : "n/a"}% of required signals reached the endpoint`);
console.log(`Multiplicity: ${grandDefects === 0 ? "no defects" : `${grandDefects} DEFECT(S) — see the per-sample MULTIPLICITY blocks above`}`);

// Coverage stays reported-only: a missing signal is scored against a ground truth
// derived from final state, and the reasons a required signal can be legitimately
// absent are still being worked out. A multiplicity defect has no such ambiguity —
// every check above is one no correct run can trip — so this is the part worth
// making a gate, and a gate is what stops the lock from silently regressing.
if (grandDefects > 0) process.exitCode = 1;
