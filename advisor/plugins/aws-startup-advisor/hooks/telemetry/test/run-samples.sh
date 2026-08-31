#!/usr/bin/env bash
#
# Telemetry hook validation against GCP sample workloads.
#
# Runs the migration telemetry hook end-to-end against real sample repos from
# SawsMigrate-SampleData, then dumps each run's event stream next to the
# artifacts that produced it so every attribute can be checked against disk.
#
# The point of using real samples rather than fixtures: fixtures agree with the
# emitter by construction. Real workloads take derivation paths nobody wrote a
# fixture for, which is how the pricing_source-is-an-object bug was found.
#
# HTTP 200 is NOT the success oracle. The handler returns 200 while publishing
# nothing on at least three paths (feature gate off, future timestamp, no event
# set), so this script reports the harness's own published=yes/no alongside the
# status code, and neither is trusted without the other.
#
# Usage
#   run-samples.sh                    run every sample in the matrix, in parallel
#   run-samples.sh 1 3 5              run only those samples
#   run-samples.sh --summarize        re-print the report from a previous run
#   run-samples.sh --keep-harness     leave harnesses running afterwards
#
# Environment
#   SAMPLE_TIMEOUT   per-sample wall clock budget, seconds (default 2400)
#   SCRATCH_ROOT     where sample copies go (default /tmp/tel-samples)
#   STATE_ROOT       where per-sample telemetry state dirs go (default /tmp/tel-runs)
#   WORKSPACE        Brazil workspace holding the harness and sample package
#   PLUGIN           plugin root to pass to --plugin-dir

set -uo pipefail

WORKSPACE="${WORKSPACE:-/home/carthick/workplace/SawsAdvisorApiModel}"
PLUGIN="${PLUGIN:-/local/home/carthick/dev/github/startups/advisor/plugins/aws-startup-advisor}"
SAMPLE_ROOT="$WORKSPACE/src/SawsMigrate-SampleData/data/sample-repos-gcp-aws-migration"
HARNESS="$WORKSPACE/local-harness/server.js"
EMIT="$PLUGIN/hooks/telemetry/emit.mjs"

SCRATCH_ROOT="${SCRATCH_ROOT:-/tmp/tel-samples}"
STATE_ROOT="${STATE_ROOT:-/tmp/tel-runs}"
LOG_ROOT="${LOG_ROOT:-/tmp/tel-logs}"
SAMPLE_TIMEOUT="${SAMPLE_TIMEOUT:-2400}"

# id | path under the sample root | harness port | short label
#
# Set B — chosen to exercise derivation paths that set A never reached, rather
# than to vary the workload again. Set A (simple-api, rag, fintech,
# multi-compute, gemini-flash, vertex-pipeline) is kept below for re-runs.
MATRIX=(
  # Golden outputs (inventory.json, cost-estimate.json, service-mapping.json) make
  # this the only sample with an ORACLE: resourceCount can be checked against a
  # known-correct 10 rather than against whatever discovery happened to produce.
  "1|iac+billing/sample-gcp-cloud-sql|4010|cloud-sql-golden"
  # Billing-only route: forces estimation-billing.json, the third branch of
  # readEstimate and the only one never exercised. Its bills total $13.35M, the
  # only path to the OVER_10K spend band. Also a space in the path and a
  # spaced-headers CSV, both parsing-robustness cases.
  "2|billing-only/GCP Test Bills|4011|billing-only"
  # No Terraform at all: tests H5 (resourceCount/hasDatabase/hasAi absent when
  # there is no gcp-resource-inventory.json) and the AI estimation route.
  "3|appcode-only/langchain-rag-knowledge-base|4012|appcode-langchain"
  # Degenerate case: appcode-only with zero code files.
  "4|appcode-only/genai-document-summarizer|4013|appcode-empty"
  # Isolates D3: google_firestore_database/_index/_document and nothing the
  # hasDatabase regex recognises.
  "5|iac/sample-gcp-firestore|4014|firestore"
  # Densest estate in the corpus: 105 resource blocks, resource-heavy rather than
  # IAM-heavy, against the resourceCount comparability finding.
  "6|iac/gcp-media-streaming-platform|4015|media-streaming"
)

# Set C — export MATRIX_SET=C. Fresh derivation paths, after the set-B defects
# (billing gcp_baseline, hasDatabase vocabulary, hasAi provenance match) were fixed.
MATRIX_C=(
  # Second golden oracle: ships inventory.json, and its cost-estimate uses
  # summary/line_items rather than current_costs — another artifact shape.
  "1|iac+billing/sample-gcp-multi-env|4010|multi-env-golden"
  # Billing in JSONL rather than CSV: an input format nothing has exercised, on
  # the gcp_baseline route that dropped every spend attribute before the fix.
  "2|billing-only/sample-gcp-only-billing-reports/enterprise-stress-test|4011|billing-jsonl"
  # AI in BOTH Terraform and application code: the one case where the type match
  # and the ai-workload-profile signal should agree rather than substitute.
  "3|iac+appcode/gcp-ai-openai-chatbot|4012|ai-both"
  # 81 resource blocks, database-heavy and compliance-shaped.
  "4|iac/gcp-healthcare-data-platform|4013|healthcare"
  # Duplicate resource addresses across modules — does resourceCount double-count?
  "5|sample-gcp-cross-module-collision|4014|module-collision"
  # Carries a live "IGNORE ALL PREVIOUS INSTRUCTIONS" payload in a .tf file.
  # Telemetry integrity test: the emitter derives attributes from artifacts the
  # agent wrote, so injected content that steers discovery can poison the data.
  "6|iac/gcp-injection-direct-override|4015|injection"
)
[ "${MATRIX_SET:-B}" = "C" ] && MATRIX=("${MATRIX_C[@]}")

# Set A, the original matrix — export MATRIX_SET=A to run it instead.
MATRIX_A=(
  "1|iac+billing/sample-gcp-simple-api|4010|simple-api"
  "2|iac+billing/sample-gcp-ml-customer-support-rag|4011|rag"
  "3|iac/gcp-fintech-platform|4012|fintech"
  "4|iac/gcp-multi-compute-cost-test|4013|multi-compute"
  "5|iac+appcode/gemini-flash-simple-classifier|4014|gemini-flash"
  "6|iac+appcode/vertex-ai-analytics-pipeline|4015|vertex-pipeline"
)
[ "${MATRIX_SET:-B}" = "A" ] && MATRIX=("${MATRIX_A[@]}")

# Headless --print cannot answer a clarifying question, so the prompt has to
# pre-authorise defaults. Stopping at the decision keeps the run to the phases
# the telemetry actually covers (Generate is opt-in by skill design anyway).
PROMPT='Migrate this GCP workload to AWS. Use the gcp-to-aws skill on the
Terraform and any application code in the current directory.

This is a NON-INTERACTIVE run: never ask me a question. Whenever the skill would
ask something, choose the most reasonable default for this codebase, record the
choice, and keep going. Run Discover, Clarify, Design and Estimate, then take the
workshop sidebar if offered and finish at the post-Estimate decision. Do NOT
generate Terraform or migration scripts. Complete the run rather than stopping
early.'

# ------------------------------------------------------------------ harness

port_pid() {
  ss -ltnp 2>/dev/null | grep ":$1 " | grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2
}

# Kill strictly by listening port. `pkill -f "server.js 4010"` matches the
# calling shell's own command line and takes the shell out with it.
kill_port() {
  local p
  p="$(port_pid "$1")"
  [ -n "$p" ] && kill "$p" 2>/dev/null && echo "  stopped harness on $1 (pid $p)"
}

start_harness() {
  local port="$1" log="$LOG_ROOT/harness-$port.log"
  # A harness started outside this script logs somewhere we cannot read, and the
  # publish=yes/no signal is the only real success oracle — so replace it rather
  # than reuse it and end up scoring the run on status codes alone.
  if [ -n "$(port_pid "$port")" ]; then
    if [ -f "$log" ]; then
      echo "  harness already up on $port with our log — reusing"
      : > "$log"
      return 0
    fi
    echo "  harness on $port is not ours (no $log) — restarting it so its log is readable"
    kill_port "$port"
    sleep 1
  fi
  : > "$log"
  ( cd "$WORKSPACE" && setsid node "$HARNESS" "$port" > "$log" 2>&1 < /dev/null & )
  for _ in $(seq 1 40); do
    sleep 0.25
    [ -n "$(port_pid "$port")" ] && break
  done
  if [ -z "$(port_pid "$port")" ]; then
    echo "  FAILED to start harness on $port; see $log" >&2
    return 1
  fi
  # 400 on an empty body is the correct liveness answer: the model rejected it,
  # which means real validation is wired up.
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 -X POST \
    "http://127.0.0.1:$port/v1/plugin-telemetry-event" \
    -H 'content-type: application/json' -d '{}')"
  echo "  harness up on $port (empty-body check: $code, expect 400)"
  STARTED_PORTS+=("$port")
}

# ------------------------------------------------------------- one sample

run_sample() {
  local id="$1" rel="$2" port="$3" label="$4"
  local scratch="$SCRATCH_ROOT/$id-$label"
  local state="$STATE_ROOT/$id-$label"
  local log="$LOG_ROOT/sample-$id-$label.log"
  local status_file="$LOG_ROOT/sample-$id-$label.status"

  rm -rf "$scratch" "$state"
  mkdir -p "$scratch" "$state"

  # Work in a copy: a run writes .migration/ and generated artifacts, and those
  # must never land in the sample package.
  cp -a "$SAMPLE_ROOT/$rel/." "$scratch/"

  # Both halves must resolve to the SAME state dir. CLAUDE_PLUGIN_DATA is
  # assigned by the host, so without this override the granting shell and the
  # hook read different files, the hook sees consent:unset, and emits nothing —
  # silently.
  export AWS_STARTUP_ADVISOR_TELEMETRY_STATE_DIR="$state"
  export AWS_STARTUP_ADVISOR_TELEMETRY_ENDPOINT="http://127.0.0.1:$port/v1/plugin-telemetry-event"
  export AWS_STARTUP_ADVISOR_TELEMETRY_DEBUG=1
  unset AWS_STARTUP_ADVISOR_TELEMETRY DO_NOT_TRACK

  # Consent is recorded per project, at `.migration/telemetry.json`, so it has to
  # be granted from inside the scratch repo with that directory already present —
  # granting from elsewhere lands in the global fallback and would leave the
  # in-repo path, which is what ships, untested.
  mkdir -p "$scratch/.migration"
  ( cd "$scratch" && node "$EMIT" consent grant ) > "$state/consent-grant.json"
  if [ ! -f "$scratch/.migration/telemetry.json" ]; then
    echo "sample $id: consent did not land in the repo, aborting this sample" >&2
    echo "consent-not-in-repo" > "$status_file"
    return 1
  fi
  # Pre-flight: prove the hook will see granted consent from the run's own cwd.
  ( cd "$scratch" && node "$EMIT" status ) > "$state/preflight-status.json"
  if ! grep -q '"consent": "granted"' "$state/preflight-status.json"; then
    echo "sample $id: consent pre-flight FAILED, aborting this sample" >&2
    echo "preflight-failed" > "$status_file"
    return 1
  fi

  local started ended rc
  started="$(date -Is)"
  # --output-format json so session_id is a structured field. SessionEnd keys
  # its abandoned-run report on the session id, so guessing it from prose would
  # make the ABORTED path untestable.
  ( cd "$scratch" && timeout "$SAMPLE_TIMEOUT" claude \
      --plugin-dir "$PLUGIN" \
      --dangerously-skip-permissions \
      --output-format json \
      --print "$PROMPT" ) > "$log" 2>&1
  rc=$?
  ended="$(date -Is)"

  # Session id, read from the structured --print output. Parsed even when we do
  # not force session-end, because the snapshot records it and the comparison
  # needs it.
  local session_id
  session_id="$(node -e '
    try {
      const j = JSON.parse(require("fs").readFileSync(process.argv[1], "utf8"));
      process.stdout.write(j.session_id ?? "");
    } catch { process.stdout.write(""); }
  ' "$log")"
  [ -n "$session_id" ] || session_id="$(grep -oE '"session_id"[": ]+[0-9a-f-]{36}' "$log" | grep -oE '[0-9a-f-]{36}' | head -1)"

  # Forcing session-end is OFF by default, and that default matters.
  #
  # Skill-frontmatter SessionEnd hooks are not honoured by the host (verified
  # 2026-08-30 on claude 2.1.251.739: a PostToolUse hook in the same frontmatter
  # fires, a SessionEnd hook in that frontmatter does not, and the same hook
  # registered via --settings does). So the product emits NO terminal event.
  #
  # Calling emit.mjs --session-end here manufactures one, which is exactly how
  # the first pass of this validation came to report "completed runs reported
  # ABORTED" when the truth is "no terminal event at all". Default off so a
  # plain run shows real product behaviour; set FORCE_SESSION_END=1 to see what
  # the session-end path *would* report.
  if [ "${FORCE_SESSION_END:-0}" = "1" ] && [ -n "$session_id" ]; then
    printf '{"session_id":"%s"}' "$session_id" | node "$EMIT" --session-end \
      >> "$state/session-end.log" 2>&1
    echo "  sample $id: session-end FORCED — terminal events below are not product behaviour"
  fi

  # Dump the event stream next to the artifacts that produced it.
  local run_dir
  run_dir="$(find "$scratch/.migration" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | head -1)"
  if [ -n "$run_dir" ] && [ -f "$state/events.jsonl" ]; then
    cp "$state/events.jsonl" "$run_dir/telemetry-events.jsonl"
  fi
  [ -f "$state/events.jsonl" ] && cp "$state/events.jsonl" "$scratch/telemetry-events.jsonl"
  # The trigger trace is the only record of hook invocations that produced no
  # event, which is what separates "ran and had nothing to say" from "never ran".
  [ -f "$state/trace.jsonl" ] && cp "$state/trace.jsonl" "$scratch/telemetry-trace.jsonl"
  [ -n "$run_dir" ] && [ -f "$state/trace.jsonl" ] && cp "$state/trace.jsonl" "$run_dir/telemetry-trace.jsonl"
  cp "$LOG_ROOT/harness-$port.log" "$scratch/harness-$port.log" 2>/dev/null

  {
    echo "id=$id"
    echo "label=$label"
    echo "rel=$rel"
    echo "port=$port"
    echo "scratch=$scratch"
    echo "state=$state"
    echo "run_dir=${run_dir:-none}"
    echo "started=$started"
    echo "ended=$ended"
    echo "claude_rc=$rc"
    echo "session_id=${session_id:-unknown}"
    echo "forced_session_end=${FORCE_SESSION_END:-0}"
  } > "$status_file"

  echo "sample $id ($label) finished rc=$rc  events=$(wc -l < "$state/events.jsonl" 2>/dev/null || echo 0)"
}

# ------------------------------------------------------------------ report

# Re-derives every reported attribute from the artifacts on disk rather than
# echoing the event back, so a derivation bug shows up as a mismatch instead of
# agreeing with itself.
summarize() {
  node - "$LOG_ROOT" "$SCRATCH_ROOT" "$STATE_ROOT" <<'NODE'
const { readFileSync, existsSync, readdirSync } = require("node:fs");
const { join } = require("node:path");
const [logRoot, scratchRoot] = process.argv.slice(2);

const readJson = (p, d = null) => { try { return JSON.parse(readFileSync(p, "utf8")); } catch { return d; } };
const kv = (p) => Object.fromEntries(readFileSync(p, "utf8").trim().split("\n")
  .map((l) => { const i = l.indexOf("="); return [l.slice(0, i), l.slice(i + 1)]; }));

const statusFiles = existsSync(logRoot)
  ? readdirSync(logRoot).filter((f) => f.endsWith(".status")).sort()
  : [];

const SPEND_KEYS = ["gcp_monthly_spend", "gcp_monthly", "gcp_monthly_usd", "heroku_monthly", "heroku_monthly_estimated"];
const band = (a) => (typeof a !== "number" || !Number.isFinite(a) || a < 0) ? undefined
  : a < 100 ? "UNDER_100" : a < 1000 ? "FROM_100_TO_1K" : a < 10000 ? "FROM_1K_TO_10K" : "OVER_10K";

const rows = [];

for (const sf of statusFiles) {
  const meta = kv(join(logRoot, sf));
  if (!meta.id) continue;
  const runDir = meta.run_dir !== "none" ? meta.run_dir : null;
  const eventsPath = join(meta.state, "events.jsonl");
  const events = existsSync(eventsPath)
    ? readFileSync(eventsPath, "utf8").trim().split("\n").filter(Boolean).map((l) => JSON.parse(l))
    : [];

  // Harness truth, keyed by occurredAt.
  //
  // NOT keyed by eventId on purpose: the emitter sends eventId and the model
  // declares it, but the handler destructures only five fields before
  // publishing, so eventId never reaches the SNS Message and cannot be used to
  // correlate here. occurredAt is millisecond Date.now() and IS forwarded,
  // which makes it the only per-event key visible on both sides.
  const harnessLog = join(scratchRoot, `${meta.id}-${meta.label}`, `harness-${meta.port}.log`);
  const harnessText = existsSync(harnessLog) ? readFileSync(harnessLog, "utf8") : "";
  const publishedById = new Map();
  const rejections = [];
  for (const rec of harnessText.split(/\n(?=\d{4}-\d\d-\d\dT)/)) {
    const pub = /published=(yes|no)/.exec(rec)?.[1];
    const occurred = /"occurredAt":(\d+)/.exec(rec)?.[1];
    const mt = /metricType=(\S+)/.exec(rec)?.[1];
    if (occurred) publishedById.set(occurred, { pub, mt });
    // A rejected request has no Message to parse an occurredAt out of, so keep
    // the rejections separately rather than dropping them from the tally.
    else if (/rejected:/.test(rec)) rejections.push(rec.trim());
  }
  const pubFor = (e) => publishedById.get(String(e.body?.occurredAt));

  console.log("=".repeat(78));
  console.log(`Sample:            ${meta.rel}`);
  console.log(`Run at:            ${meta.started} -> ${meta.ended}  (claude rc=${meta.claude_rc})`);

  const phaseStatus = runDir ? readJson(join(runDir, ".phase-status.json")) : null;
  console.log(`Phases reached:    ${phaseStatus
    ? Object.entries(phaseStatus.phases ?? {}).map(([k, v]) => `${k}=${v}`).join(" ") +
      `  current=${phaseStatus.current_phase} run_mode=${phaseStatus.run_mode ?? "-"}`
    : "no .phase-status.json written"}`);

  const codes = events.map((e) => e.status);
  const all200 = events.length > 0 && codes.every((c) => c === 200);
  const pubs = events.map((e) => pubFor(e)?.pub ?? "?");
  const allPub = events.length > 0 && pubs.every((p) => p === "yes");
  console.log(`Events (n):        ${events.length}  all 200? ${events.length ? (all200 ? "y" : "n") : "n/a"}  all published=yes? ${events.length ? (allPub ? "y" : "n") : "n/a"}`);

  console.log("Event stream:");
  const runIds = new Set(), eventIds = new Set();
  for (const e of events) {
    const ma = e.body?.pluginTelemetryEvent?.migrationActivity ?? {};
    runIds.add(ma.runId); eventIds.add(e.body?.eventId);
    const p = pubFor(e);
    console.log(`  ${String(e.status)} pub=${p?.pub ?? "?"} ${p?.mt ? `mt=${p.mt} ` : ""}${(ma.eventName ?? "?").padEnd(16)} ${(ma.phase ?? "-").padEnd(9)} ${(ma.status ?? "-").padEnd(8)} ${JSON.stringify(ma.attributes ?? {})}`);
  }
  console.log(`  runIds=${runIds.size} (want 1)  distinct eventIds=${eventIds.size} of ${events.length} (want equal)`);
  if (rejections.length) {
    console.log(`  REJECTED BY MODEL (${rejections.length}) — a 400 here is a derivation defect, not a bad sample:`);
    for (const r of rejections) console.log(`    ${r.replace(/\n\s*/g, " ")}`);
  }

  // ---- artifacts on disk
  const inv = runDir ? readJson(join(runDir, "gcp-resource-inventory.json")) : null;
  const invResources = Array.isArray(inv) ? inv : inv?.resources;
  const est = runDir
    ? ["estimation-infra.json", "estimation-ai.json", "estimation-billing.json"]
        .map((n) => readJson(join(runDir, n))).find(Boolean)
    : null;
  const prefs = runDir ? readJson(join(runDir, "preferences.json")) : null;
  const aiProfile = runDir ? readJson(join(runDir, "ai-workload-profile.json")) : null;
  const cc = est?.current_costs ?? {};
  const spendKey = SPEND_KEYS.find((k) => cc[k] != null);

  console.log("Artifacts on disk:");
  console.log(`  resourceCount(disk)     = ${Array.isArray(invResources) ? invResources.length : "no inventory"}`);
  console.log(`  current_costs.source    = ${cc.source ?? "-"}`);
  console.log(`  current_costs.${spendKey ?? "<none>"} = ${spendKey ? cc[spendKey] : "-"}  -> band ${band(cc[spendKey]) ?? "undefined"}`);
  console.log(`  recommendation.outcome  = ${est?.recommendation?.outcome ?? "-"}`);
  console.log(`  pricing_source          = ${JSON.stringify(est?.pricing_source ?? est?.projected_costs?.pricing_source ?? null)}`);
  console.log(`  preferences.migration_type = ${prefs?.metadata?.migration_type ?? "-"}`);
  console.log(`  ai-workload-profile.json   = ${aiProfile ? "PRESENT" : "absent"}`);
  console.log(`  estimate artifact          = ${est ? "present" : "absent"}`);

  // ---- event vs disk
  const discover = events.map((e) => e.body?.pluginTelemetryEvent?.migrationActivity).find((m) => m?.phase === "DISCOVER");
  const estimate = events.map((e) => e.body?.pluginTelemetryEvent?.migrationActivity).find((m) => m?.phase === "ESTIMATE");
  const diverged = [];
  if (discover && Array.isArray(invResources) &&
      discover.attributes?.resourceCount !== Math.min(invResources.length, 10000)) {
    diverged.push(`resourceCount event=${discover.attributes?.resourceCount} disk=${invResources.length}`);
  }
  if (estimate && spendKey && estimate.attributes?.spendBand !== band(cc[spendKey])) {
    diverged.push(`spendBand event=${estimate.attributes?.spendBand} disk=${band(cc[spendKey])}`);
  }
  if (estimate && cc.source && !estimate.attributes?.spendBasis) {
    diverged.push(`spendBasis missing though current_costs.source=${cc.source}`);
  }
  // The interesting case for H1: AI is real on disk but invisible to the event.
  const aiOnDisk = !!aiProfile || (runDir && existsSync(join(runDir, "..", "..", "app")));
  if (discover && aiOnDisk && discover.attributes?.hasAi === false) {
    diverged.push(`hasAi=false though AI evidence exists on disk (ai-workload-profile.json ${aiProfile ? "present" : "absent"})`);
  }
  console.log(`Attributes correct vs disk?   ${diverged.length ? "n — " + diverged.join("; ") : "y"}`);

  const terminals = events.map((e) => e.body?.pluginTelemetryEvent?.migrationActivity)
    .filter((m) => m?.eventName === "RUN_COMPLETED");
  const started = events.filter((e) => e.body?.pluginTelemetryEvent?.migrationActivity?.eventName === "RUN_STARTED").length;
  const forced = meta.forced_session_end === "1";
  console.log(`Terminal events:  ${terminals.length} (want exactly 1) -> ${terminals.map((t) => t.status).join(",") || "none"}` +
    (forced ? "   [session-end FORCED — not product behaviour]" : "   [product behaviour: none expected, see D1b]"));
  console.log(`RUN_STARTED:      ${started} (want exactly 1)`);

  rows.push({
    sample: `${meta.id} ${meta.label}`,
    events: events.length,
    all200: events.length ? (all200 ? "y" : "n") : "-",
    allPub: events.length ? (allPub ? "y" : "n") : "-",
    resourceCount: discover?.attributes?.resourceCount ?? "-",
    hasDatabase: discover?.attributes?.hasDatabase ?? "-",
    hasAi: discover?.attributes?.hasAi ?? "-",
    spendBand: estimate?.attributes?.spendBand ?? "-",
    spendBasis: estimate?.attributes?.spendBasis ?? "-",
    terminal: terminals.length === 1 ? terminals[0].status : (terminals.length ? `x${terminals.length}` : "none"),
    defects: diverged.length,
  });
}

console.log("\n" + "=".repeat(78));
console.log("SUMMARY (section 6)\n");
const cols = ["sample", "events", "all200", "allPub", "resourceCount", "hasDatabase", "hasAi", "spendBand", "spendBasis", "terminal", "defects"];
const w = cols.map((c) => Math.max(c.length, ...rows.map((r) => String(r[c]).length)));
console.log(cols.map((c, i) => c.padEnd(w[i])).join("  "));
console.log(w.map((n) => "-".repeat(n)).join("  "));
for (const r of rows) console.log(cols.map((c, i) => String(r[c]).padEnd(w[i])).join("  "));
NODE
}

# -------------------------------------------------------------------- main

KEEP_HARNESS=0
WANTED=()
for arg in "$@"; do
  case "$arg" in
    --summarize) summarize; exit 0 ;;
    --keep-harness) KEEP_HARNESS=1 ;;
    [1-9]) WANTED+=("$arg") ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

for required in "$HARNESS" "$EMIT" "$SAMPLE_ROOT"; do
  [ -e "$required" ] || { echo "missing: $required" >&2; exit 1; }
done
command -v claude >/dev/null || { echo "claude CLI not on PATH" >&2; exit 1; }

mkdir -p "$SCRATCH_ROOT" "$STATE_ROOT" "$LOG_ROOT"
STARTED_PORTS=()
PIDS=()

echo "Starting harnesses"
for entry in "${MATRIX[@]}"; do
  IFS='|' read -r id rel port label <<< "$entry"
  if [ ${#WANTED[@]} -gt 0 ]; then
    printf '%s\n' "${WANTED[@]}" | grep -qx "$id" || continue
  fi
  rm -f "$LOG_ROOT/sample-$id-$label.status"
  start_harness "$port" || exit 1
done

echo
echo "Launching sample runs (timeout ${SAMPLE_TIMEOUT}s each)"
for entry in "${MATRIX[@]}"; do
  IFS='|' read -r id rel port label <<< "$entry"
  if [ ${#WANTED[@]} -gt 0 ]; then
    printf '%s\n' "${WANTED[@]}" | grep -qx "$id" || continue
  fi
  run_sample "$id" "$rel" "$port" "$label" &
  PIDS+=("$!")
  echo "  sample $id ($label) -> pid $! port $port"
done

# Wait on the RUN pids specifically. A bare `wait` would also wait on any
# harness that is a job of this shell and never return.
echo
for pid in "${PIDS[@]}"; do wait "$pid"; done

echo
echo "All sample runs finished."
if [ "$KEEP_HARNESS" -eq 0 ]; then
  echo "Stopping harnesses this run started"
  for port in "${STARTED_PORTS[@]:-}"; do [ -n "$port" ] && kill_port "$port"; done
fi

echo
summarize
