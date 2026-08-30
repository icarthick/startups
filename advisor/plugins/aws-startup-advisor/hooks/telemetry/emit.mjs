#!/usr/bin/env node
/**
 * Migration telemetry emitter (Claude Code hook).
 *
 * Registered by each migration skill's frontmatter as a PostToolUse hook on
 * writes to `.phase-status.json`. That file is the skills' own phase tracker, so
 * a write to it IS a phase transition — the emitter diffs the new contents
 * against the previous snapshot and reports the transitions it finds. Nothing is
 * inferred from the conversation and no instruction has to be followed, so
 * emission does not depend on the agent remembering to do anything.
 *
 * Opt-in: emits nothing at all, not even locally, unless consent is granted.
 *
 * Fail-open: every path exits 0. A telemetry problem must never surface to the
 * customer or interrupt a migration. The hook is declared `async` so it cannot
 * add latency either.
 *
 * Usage
 *   emit.mjs --skill GCP_TO_AWS        hook mode; hook JSON arrives on stdin
 *   emit.mjs consent get|grant|revoke  consent state (called from skill prose)
 *   emit.mjs status                    print state for debugging
 *
 * Environment
 *   AWS_STARTUP_ADVISOR_TELEMETRY_ENDPOINT  where to POST; unset = no network
 *   AWS_STARTUP_ADVISOR_TELEMETRY_DEBUG=1   also append events to a local log
 *   AWS_STARTUP_ADVISOR_TELEMETRY_STATE_DIR override the state dir (testing)
 *   AWS_STARTUP_ADVISOR_TELEMETRY=0         opt out
 *   DO_NOT_TRACK=1                          opt out
 */

import { readFileSync, writeFileSync, mkdirSync, existsSync, appendFileSync } from "node:fs";
import { homedir } from "node:os";
import { join, dirname, basename } from "node:path";
import { randomUUID } from "node:crypto";

const POST_TIMEOUT_MS = 3000;
const PLUGIN_VERSION = "2.0.0";
const SOURCE = "CLAUDE_CODE";

/** Persistent state dir. CLAUDE_PLUGIN_DATA survives plugin updates, unlike
 *  CLAUDE_PLUGIN_ROOT; the home-dir fallback covers non-hook invocations.
 *
 *  The explicit override exists because CLAUDE_PLUGIN_DATA is assigned by the
 *  host, so without it there is no way to seed consent from outside a session —
 *  which testing needs, and which a non-hook host would need too. */
const stateDir = () =>
  process.env.AWS_STARTUP_ADVISOR_TELEMETRY_STATE_DIR ||
  process.env.CLAUDE_PLUGIN_DATA ||
  join(homedir(), ".aws-startups-plugins");

const consentPath = () => join(stateDir(), "telemetry.json");
const runPath = (migrationId) => join(stateDir(), "runs", `${migrationId}.json`);

const readJson = (p, fallback = null) => {
  try {
    return JSON.parse(readFileSync(p, "utf8"));
  } catch {
    return fallback;
  }
};

const writeJson = (p, value) => {
  mkdirSync(dirname(p), { recursive: true });
  writeFileSync(p, JSON.stringify(value, null, 2));
};

// ---------------------------------------------------------------- consent

const optedOutByEnv = () =>
  process.env.DO_NOT_TRACK === "1" || process.env.AWS_STARTUP_ADVISOR_TELEMETRY === "0";

const readConsent = () => readJson(consentPath(), { consent: "unset" });

const setConsent = (granted) => {
  const existing = readConsent();
  const record = {
    consent: granted ? "granted" : "revoked",
    // installId is minted once and kept across revoke/re-grant so the same
    // install is not counted as two.
    installId: existing.installId ?? randomUUID(),
    consentedAt: new Date().toISOString(),
    version: 1,
  };
  writeJson(consentPath(), record);
  return record;
};

// ------------------------------------------------- phase-status vocabulary

/** Statuses that mean a phase is finished. The DSL-governed skills may resolve a
 *  phase without running it, and those count as resolved for the backbone walk,
 *  so they are transitions we must report rather than ignore. */
const RESOLVED_STATUS = {
  completed: "SUCCESS",
  skipped: "SKIPPED",
  not_applicable: "NOT_APPLICABLE",
  failed: "FAILED",
};

const PHASES = new Set([
  "DISCOVER",
  "CLARIFY",
  "DESIGN",
  "ESTIMATE",
  "WORKSHOP",
  "GENERATE",
  "FEEDBACK",
]);

const toPhaseEnum = (name) => {
  const upper = String(name).toUpperCase();
  return PHASES.has(upper) ? upper : undefined;
};

// ------------------------------------------------------ attribute mapping

/**
 * Map a value found in an artifact onto a model enum.
 *
 * Returns undefined when the value is not recognised, and callers omit the
 * attribute in that case. This matters: the API rejects the whole request on one
 * invalid enum member, so passing a drifted value straight through would lose
 * the entire event rather than one field. The skills' vocabularies live in prose
 * and can change without notice, so unknown-means-omit is the safe default.
 */
const mapEnum = (table, value) =>
  value == null ? undefined : table[String(value).toLowerCase()];

const PRICING_SOURCE = {
  live: "LIVE",
  cached: "CACHED",
  cached_fallback: "CACHED_FALLBACK",
  cached_stale: "CACHED_STALE",
  unavailable: "UNAVAILABLE",
};

const RECOMMENDATION_OUTCOME = {
  go: "GO",
  conditional_go: "CONDITIONAL_GO",
  defer: "DEFER",
  stay: "STAY",
};

const CLARIFY_MODE = { fast: "FAST", wizard: "WIZARD", full: "FULL", ai_only: "AI_ONLY" };

/**
 * Pricing provenance, which the estimate artifact records in one of two shapes.
 *
 * Current estimates write an object — `{ status, fallback_staleness: { is_stale
 * } }` — and staleness is a separate boolean rather than a distinct status, so
 * CACHED_STALE has to be composed from the two. Older prose describes a bare
 * string, which is still accepted.
 */
const toPricingSource = (raw) => {
  if (raw == null) return undefined;
  const isObject = typeof raw === "object";
  const mapped = mapEnum(PRICING_SOURCE, isObject ? raw.status : raw);
  if (!mapped) return undefined;
  const stale = isObject && raw.fallback_staleness?.is_stale === true;
  return mapped === "CACHED" && stale ? "CACHED_STALE" : mapped;
};

/** Monthly spend on the SOURCE platform, which is what spendBand means. The key
 *  name is inconsistent across skills and phases, so try the known spellings. */
const SOURCE_SPEND_KEYS = [
  "gcp_monthly_spend",
  "gcp_monthly",
  "gcp_monthly_usd",
  "heroku_monthly",
  "heroku_monthly_estimated",
];

const toSpendBand = (amount) => {
  if (typeof amount !== "number" || !Number.isFinite(amount) || amount < 0) return undefined;
  if (amount < 100) return "UNDER_100";
  if (amount < 1000) return "FROM_100_TO_1K";
  if (amount < 10000) return "FROM_1K_TO_10K";
  return "OVER_10K";
};

const SKILL_INVENTORY = {
  GCP_TO_AWS: { inventory: "gcp-resource-inventory.json", provider: "GCP" },
  HEROKU_TO_AWS: { inventory: "heroku-resource-inventory.json", provider: "HEROKU" },
};

/** Read the first estimation artifact that exists — the route taken (infra, AI
 *  or billing-only) decides which one the skill wrote. */
const readEstimate = (dir) => {
  for (const name of ["estimation-infra.json", "estimation-ai.json", "estimation-billing.json"]) {
    const found = readJson(join(dir, name));
    if (found) return found;
  }
  return null;
};

/**
 * Derive attributes from the artifacts already on disk.
 *
 * Everything here is a lookup or a pure function over a number — no inference,
 * so the values are reproducible and reviewable rather than model-generated.
 *
 * Scoped to the phase that produced each fact. Attaching the whole set to every
 * event would put a cost recommendation on a DISCOVER event, which makes the
 * funnel ambiguous about which phase the signal came from, and would keep
 * restating facts that only need reporting once per run.
 */
const deriveAttributes = (dir, skill, event) => {
  const attributes = {};
  const spec = SKILL_INVENTORY[skill];

  // A property of the run itself, so it belongs on every event.
  if (spec) attributes.sourceProvider = spec.provider;

  if (event.phase === "DISCOVER") {
    const inventory = spec ? readJson(join(dir, spec.inventory)) : null;
    const resources = Array.isArray(inventory) ? inventory : inventory?.resources;
    if (Array.isArray(resources)) {
      // Range-bounded in the model; clamp rather than emit an invalid value.
      attributes.resourceCount = Math.min(resources.length, 10000);
      const types = JSON.stringify(resources).toLowerCase();
      attributes.hasDatabase = /sql|postgres|rds|aurora|dynamo|redis|mysql|mongo/.test(types);
      attributes.hasAi = /vertex|openai|bedrock|anthropic|gemini|llm|sagemaker/.test(types);
    }
  }

  if (event.phase === "CLARIFY") {
    const preferences = readJson(join(dir, "preferences.json"));
    const clarifyMode = mapEnum(CLARIFY_MODE, preferences?.metadata?.migration_type);
    if (clarifyMode) attributes.clarifyMode = clarifyMode;
  }

  if (event.phase === "ESTIMATE") {
    const estimate = readEstimate(dir);
    if (estimate) {
      const outcome = mapEnum(RECOMMENDATION_OUTCOME, estimate.recommendation?.outcome);
      if (outcome) attributes.recommendationOutcome = outcome;

      const pricing = toPricingSource(
        estimate.pricing_source ?? estimate.projected_costs?.pricing_source,
      );
      if (pricing) attributes.pricingSource = pricing;

      const current = estimate.current_costs ?? {};
      for (const key of SOURCE_SPEND_KEYS) {
        const band = toSpendBand(current[key]);
        if (band) {
          attributes.spendBand = band;
          break;
        }
      }
    }
  }

  return Object.keys(attributes).length ? attributes : undefined;
};

// ------------------------------------------------------------- transitions

/**
 * Compare the previous snapshot of `phases` with the new one and return the
 * events that transition implies.
 */
const diffToEvents = (previous, current) => {
  const events = [];
  const before = previous?.phases ?? null;
  const after = current.phases ?? {};

  // No snapshot means this is the first write of the run.
  if (before === null) events.push({ eventName: "RUN_STARTED" });

  for (const [name, status] of Object.entries(after)) {
    if (before && before[name] === status) continue;
    const mapped = RESOLVED_STATUS[String(status).toLowerCase()];
    const phase = toPhaseEnum(name);
    if (!mapped || !phase) continue; // pending / in_progress / unknown phase
    events.push({ eventName: "PHASE_COMPLETED", phase, status: mapped });
  }

  const wasComplete = previous?.current_phase === "complete";
  if (current.current_phase === "complete" && !wasComplete) {
    // run_mode "decide" is a deliberate decision-only finish, not an abandoned
    // run — without it the two are indistinguishable in the funnel.
    events.push({
      eventName: "RUN_COMPLETED",
      status: "SUCCESS",
      runMode: current.run_mode === "decide_and_execute" ? "DECIDE_AND_EXECUTE" : "DECIDE",
    });
  }

  return events;
};

// -------------------------------------------------------------- transport

const post = async (endpoint, body) => {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), POST_TIMEOUT_MS);
  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    return response.status;
  } catch {
    return null; // offline, timeout, DNS — silently give up
  } finally {
    clearTimeout(timer);
  }
};

const debugLog = (line) => {
  if (process.env.AWS_STARTUP_ADVISOR_TELEMETRY_DEBUG !== "1") return;
  try {
    const p = join(stateDir(), "events.jsonl");
    mkdirSync(dirname(p), { recursive: true });
    appendFileSync(p, `${JSON.stringify(line)}\n`);
  } catch {
    /* ignore */
  }
};

// ------------------------------------------------------------- hook mode

const runHook = async (skill) => {
  const raw = readFileSync(0, "utf8");
  const hook = JSON.parse(raw);

  const filePath = hook?.tool_input?.file_path;
  if (!filePath || basename(filePath) !== ".phase-status.json") return;

  const consent = readConsent();
  if (consent.consent !== "granted" || optedOutByEnv()) return;

  const dir = dirname(filePath);
  const absolute = filePath.startsWith("/") ? filePath : join(hook.cwd ?? process.cwd(), filePath);
  const current = readJson(absolute);
  if (!current?.migration_id) return;

  // A second migration skill invoked in the same session leaves both skills'
  // hooks registered, so confirm this run belongs to the skill that registered
  // this hook before reporting anything under its name.
  const spec = SKILL_INVENTORY[skill];
  const ownDir = filePath.startsWith("/") ? dirname(absolute) : dir;
  const other = Object.entries(SKILL_INVENTORY).find(([name]) => name !== skill)?.[1];
  if (spec && other && !existsSync(join(ownDir, spec.inventory)) && existsSync(join(ownDir, other.inventory))) {
    return;
  }

  const snapshotPath = runPath(current.migration_id);
  const snapshot = readJson(snapshotPath);
  const events = diffToEvents(snapshot, current);

  // runId is minted here, not derived from migration_id: that marker is
  // MMDD-HHMM, so two customers starting in the same minute would otherwise
  // share a runId on a shared backend.
  const runId = snapshot?.runId ?? randomUUID();
  const endpoint = process.env.AWS_STARTUP_ADVISOR_TELEMETRY_ENDPOINT;

  for (const event of events) {
    const { runMode, ...rest } = event;
    const attributes = deriveAttributes(ownDir, skill, event) ?? {};
    if (runMode) attributes.runMode = runMode;

    const body = {
      installId: consent.installId,
      source: SOURCE,
      pluginVersion: PLUGIN_VERSION,
      occurredAt: Date.now(),
      eventId: randomUUID(), // fresh per emission: a genuine phase re-run is a
      // real second occurrence and must not dedup away
      pluginTelemetryEvent: {
        migrationActivity: {
          ...rest,
          skill,
          runId,
          ...(Object.keys(attributes).length ? { attributes } : {}),
        },
      },
    };

    const status = endpoint ? await post(endpoint, body) : null;
    debugLog({ at: new Date().toISOString(), status, body });
  }

  writeJson(snapshotPath, {
    runId,
    migration_id: current.migration_id,
    current_phase: current.current_phase,
    run_mode: current.run_mode,
    phases: current.phases ?? {},
  });
};

// ------------------------------------------------------------------- main

const main = async () => {
  const args = process.argv.slice(2);

  if (args[0] === "consent") {
    const action = args[1] ?? "get";
    if (action === "grant") return console.log(JSON.stringify(setConsent(true)));
    if (action === "revoke") return console.log(JSON.stringify(setConsent(false)));
    return console.log(JSON.stringify(readConsent()));
  }

  if (args[0] === "status") {
    return console.log(
      JSON.stringify(
        {
          stateDir: stateDir(),
          consent: readConsent(),
          endpoint: process.env.AWS_STARTUP_ADVISOR_TELEMETRY_ENDPOINT ?? null,
          optedOutByEnv: optedOutByEnv(),
        },
        null,
        2,
      ),
    );
  }

  const skillIndex = args.indexOf("--skill");
  const skill = skillIndex === -1 ? undefined : args[skillIndex + 1];
  if (!skill) return; // no skill, nothing we could attribute an event to
  await runHook(skill);
};

// Fail-open is the whole contract: swallow everything and exit 0.
main().catch(() => {}).finally(() => process.exit(0));
