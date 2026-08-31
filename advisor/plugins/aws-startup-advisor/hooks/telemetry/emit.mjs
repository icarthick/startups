#!/usr/bin/env node
/**
 * Migration telemetry emitter (Claude Code and Cursor hook).
 *
 * Registered as a post-write hook on `.phase-status.json` — by skill frontmatter
 * on Claude Code, by `hooks.json` on Cursor. That file is the skills' own phase tracker, so
 * a write to it IS a phase transition — the emitter diffs the new contents
 * against the previous snapshot and reports the transitions it finds. Nothing is
 * inferred from the conversation and no instruction has to be followed, so
 * emission does not depend on the agent remembering to do anything.
 *
 * Opt-in: emits nothing at all, not even locally, unless consent is granted.
 *
 * State lives where the customer can see it. The consent record sits at
 * `.migration/telemetry.json` and each run's snapshot at
 * `.migration/<id>/.telemetry-snapshot.json`, so the decision and the reported
 * state are both inspectable in the directory the customer already works in.
 * Only `installId` is kept outside, in the plugin state dir: scoping identity to
 * a repo would count one customer with three projects as three installs.
 *
 * Fail-open: every path exits 0. A telemetry problem must never surface to the
 * customer or interrupt a migration. The hook is declared `async` so it cannot
 * add latency either.
 *
 * Usage
 *   emit.mjs --skill GCP_TO_AWS        PostToolUse mode; hook JSON on stdin
 *   emit.mjs --skill X --reconcile     Stop mode; reconcile disk against snapshot
 *   emit.mjs --session-end             SessionEnd mode; final reconcile
 *   emit.mjs consent get|grant|revoke  consent state (called from skill prose)
 *   emit.mjs status                    print state for debugging
 *
 * Why two hook modes rather than one
 *   PostToolUse only fires for tools named in its matcher, and the skills update
 *   `.phase-status.json` from Bash/python as readily as from Write — a read-merge
 *   -write is natural to express as a python one-liner. Those writes are
 *   invisible to the matcher, so the snapshot silently stops advancing and every
 *   later transition is lost. Measured against the GCP sample corpus, that cost
 *   37% of all expected events, including whole runs that emitted nothing at all.
 *
 *   Reconcile mode closes it by working from state instead of from tool calls: on
 *   Stop it re-reads `.phase-status.json` and diffs it against the snapshot, so
 *   the writer does not matter. It is idempotent — if PostToolUse already
 *   advanced the snapshot there is no delta and nothing is sent — so both hooks
 *   are registered and cover each other: PostToolUse delivers incrementally in
 *   case the session is killed, Stop catches whatever the matcher missed.
 *
 * Environment
 *   AWS_STARTUP_ADVISOR_TELEMETRY_ENDPOINT  where to POST; unset = no network
 *   AWS_STARTUP_ADVISOR_TELEMETRY_DEBUG=1   append events AND a per-invocation
 *                                           trigger trace to the state dir
 *   AWS_STARTUP_ADVISOR_TELEMETRY_STATE_DIR override the state dir (testing)
 *   AWS_STARTUP_ADVISOR_TELEMETRY=0         opt out
 *   DO_NOT_TRACK=1                          opt out
 *   AWS_STARTUP_ADVISOR_TELEMETRY_SOURCE    force the reported host (testing)
 */

import {
  readFileSync,
  writeFileSync,
  mkdirSync,
  existsSync,
  appendFileSync,
  readdirSync,
} from "node:fs";
import { homedir } from "node:os";
import { join, dirname, basename } from "node:path";
import { fileURLToPath } from "node:url";
import { randomUUID } from "node:crypto";

const POST_TIMEOUT_MS = 3000;

/**
 * Which host is running us, as a modelled `PluginSource` member.
 *
 * Derived from the environment rather than hardcoded, because the same script is
 * registered by two hosts with different registration mechanisms. Cursor always
 * exports CURSOR_VERSION and CURSOR_PROJECT_DIR; it also exports
 * CLAUDE_PROJECT_DIR as a compatibility alias, so keying on CLAUDE_* would
 * misattribute every Cursor event as Claude Code.
 *
 * The default stays CLAUDE_CODE so an unrecognised host is never reported as a
 * host it is not, and `source` is @required so it cannot simply be omitted.
 */
const PLUGIN_SOURCES = new Set(["CLAUDE_CODE", "CODEX", "CURSOR", "KIRO", "OTHER"]);

const detectSource = () => {
  const override = process.env.AWS_STARTUP_ADVISOR_TELEMETRY_SOURCE;
  // Validated against the modelled members: `source` is @required, so an
  // unrecognised override would fail request validation and cost the whole event
  // rather than one field.
  if (override && PLUGIN_SOURCES.has(override)) return override;
  if (process.env.CURSOR_VERSION || process.env.CURSOR_PROJECT_DIR) return "CURSOR";
  return "CLAUDE_CODE";
};

const SOURCE = detectSource();

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

/**
 * Where a run's snapshot lives: inside the run directory it describes.
 *
 * Two reasons. It is inspectable — the customer can open the same directory they
 * already look at and see exactly what was reported about it, which is hard to
 * argue with as a transparency property for opt-in telemetry. And the path is
 * inherently unique, which fixes a real collision: the snapshot used to be keyed
 * by `migration_id` alone in a shared directory, and `migration_id` is MMDD-HHMM
 * at minute resolution. Two repos whose migrations began in the same minute
 * shared one snapshot file; the second run diffed against the first run's state,
 * found no change, and emitted NOTHING while corrupting the snapshot's runId.
 *
 * Dot-prefixed and inside the already-gitignored `.migration/` tree, so it does
 * not appear in the customer's diffs.
 */
const runPath = (runDir) => join(runDir, ".telemetry-snapshot.json");

/**
 * Consent lives at the root of `.migration/`, beside the runs it governs.
 *
 * Same transparency argument: the decision is visible where the work is, rather
 * than in a hidden directory elsewhere on the machine.
 *
 * `installId` is deliberately NOT scoped here — see `installId()`. A per-repo
 * identifier would make one customer with three repos look like three customers
 * and silently inflate every adoption number.
 */
const consentPathFor = (migrationRoot) => join(migrationRoot, "telemetry.json");

/** Global fallback, for invocations with no migration directory in scope. */
const globalConsentPath = () => join(stateDir(), "telemetry.json");
const installIdPath = () => join(stateDir(), "install.json");

/** Read the shipped plugin version rather than carrying a copy: a hardcoded
 *  version silently misattributes every event after the next release bump, which
 *  is invisible in the data and breaks any per-release comparison. */
const pluginRoot = () =>
  process.env.CLAUDE_PLUGIN_ROOT || join(dirname(fileURLToPath(import.meta.url)), "..", "..");

const pluginVersion = () =>
  // Fallback is a valid semver so a missing manifest cannot fail model
  // validation and cost the event.
  readJson(join(pluginRoot(), ".claude-plugin", "plugin.json"), {}).version ?? "0.0.0";

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

/**
 * Locate the `.migration/` root, walking up from a starting directory.
 *
 * The skills `cd` into `.migration/<id>/` to work on artifacts with relative
 * paths, so the starting point may be the run dir, the repo root, or somewhere
 * between. Bounded depth; returns null when there is no migration tree, which is
 * the normal case for a plain `emit.mjs status` outside a project.
 */
const findMigrationRoot = (start) => {
  let dir = start;
  for (let depth = 0; depth < 6; depth++) {
    if (basename(dir) === ".migration") return dir;
    const candidate = join(dir, ".migration");
    if (existsSync(candidate)) return candidate;
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return null;
};

/**
 * The install identifier, minted once per machine and never per repo.
 *
 * Kept outside `.migration/` on purpose. Consent is a per-project decision and is
 * stored with the project, but identity is not: if `installId` were scoped to a
 * repo, one customer migrating three repos would appear as three installs, and
 * every adoption and funnel figure would be inflated by however many projects
 * people happen to have. It is also stable across revoke/re-grant so the same
 * install is never counted twice.
 */
const installId = () => {
  const existing = readJson(installIdPath());
  if (existing?.installId) return existing.installId;
  const minted = { installId: randomUUID(), createdAt: new Date().toISOString() };
  try {
    writeJson(installIdPath(), minted);
  } catch {
    /* ignore — a read-only state dir must not break emission */
  }
  return minted.installId;
};

/**
 * Read the consent decision for a given migration tree.
 *
 * Falls back to the global record so a consent granted before this change, or
 * seeded outside any project, still applies.
 */
const readConsentAt = (migrationRoot) => {
  const scoped = migrationRoot && readJson(consentPathFor(migrationRoot));
  if (scoped?.consent) return scoped;
  return readJson(globalConsentPath(), { consent: "unset" });
};

const readConsent = () => readConsentAt(findMigrationRoot(process.cwd()));

const setConsent = (granted, migrationRoot) => {
  const record = {
    consent: granted ? "granted" : "revoked",
    installId: installId(),
    consentedAt: new Date().toISOString(),
    version: 1,
  };
  // Written where the runs are when there is a migration tree, so the customer
  // can see the decision beside the work it governs; globally otherwise.
  writeJson(migrationRoot ? consentPathFor(migrationRoot) : globalConsentPath(), record);
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

/**
 * Workload-shape detection, matched against resource TYPES only.
 *
 * Not against the serialised inventory. The inventory carries the discover
 * phase's own metadata alongside the customer's resources, including
 * `classification_source: "llm_inference"` — meaning "an LLM inferred this
 * classification", not "the customer runs AI". Matching /llm/ over the whole blob
 * therefore reported hasAi:true on three separate AI-free samples (a pure-compute
 * estate, a fintech platform, and a media pipeline). Types are the provider's
 * product identity and carry no such provenance.
 */
const AI_TYPE =
  /vertex|aiplatform|notebooks|discovery_engine|automl|ml_engine|dialogflow|document_ai|bedrock|sagemaker|comprehend/;

/**
 * Managed-database detection.
 *
 * The GCP product names matter and were absent: the original vocabulary listed
 * AWS names and engine names only, so a dedicated Firestore estate reported
 * hasDatabase:false. Kept in one place so both providers' names stay together.
 */
const DB_TYPE =
  /sql|postgres|mysql|mongo|redis|firestore|spanner|bigtable|datastore|memorystore|alloydb|rds|aurora|dynamo|elasticache|documentdb/;

const resourceTypes = (resources) =>
  resources
    .map((r) => String(r?.type ?? r?.resource_type ?? ""))
    .join(" ")
    .toLowerCase();

/** Monthly spend on the SOURCE platform, which is what spendBand means. The key
 *  name is inconsistent across skills, phases and routes, so try the known
 *  spellings. `total_monthly_spend` is the billing-only route's name for a
 *  MEASURED figure — omitting it dropped spend telemetry for exactly the segment
 *  whose spend is a bill rather than an estimate. */
const SOURCE_SPEND_KEYS = [
  "gcp_monthly_spend",
  "gcp_monthly",
  "gcp_monthly_usd",
  "total_monthly_spend",
  "gcp_total_monthly",
  "total_monthly",
  "gcp_monthly_ai_spend",
  "total_current_ai_monthly",
  "heroku_monthly",
  "heroku_monthly_estimated",
];

/** How the source-spend figure was arrived at. Without this, spendBand is not
 *  safely comparable: an inventory estimate prices only resources with a
 *  standing charge, so a workload that is mostly usage-based reads far cheaper
 *  than its actual bill. Analysis needs to be able to keep the measured ones. */
const SPEND_BASIS = {
  billing_data: "BILLING_DATA",
  inventory_estimate: "INVENTORY_ESTIMATE",
  live_prices_plus_cache: "LIVE_PRICES_PLUS_CACHE",
  pricing_cache: "PRICING_CACHE",
  user_provided: "USER_PROVIDED",
  unavailable: "UNAVAILABLE",
  // The AI estimate route prices token volume, not infrastructure. Unmapped, this
  // cost every AI-primary run its entire spend signal: the band is suppressed when
  // its basis is unknown, so both fields vanished together.
  estimated_from_token_volume: "TOKEN_VOLUME_ESTIMATE",
  // A band the skill fell back to with nothing to measure. Kept separate from
  // USER_PROVIDED because the artifact itself calls it "not a user statement and
  // not a measurement" — conflating them would dress a placeholder as an answer.
  preferences: "DEFAULTED",
};

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

/**
 * Read EVERY estimation artifact present, in preference order.
 *
 * Returning only the first match was wrong whenever a run wrote more than one.
 * An AI-primary migration writes both `estimation-ai.json` and
 * `estimation-infra.json`; taking infra first costed one such workload from a
 * defaulted $300 placeholder that the artifact itself labelled "NOT
 * DECISION-GRADE", while the computed $11.80 sat unread in the AI file — two
 * spend bands wrong. Each attribute is now taken from the first artifact that
 * actually supplies it.
 */
const readEstimates = (dir) =>
  ["estimation-infra.json", "estimation-ai.json", "estimation-billing.json"]
    .map((name) => readJson(join(dir, name)))
    .filter(Boolean);

/**
 * Where a route records the source-platform cost.
 *
 * The infra and AI routes use `current_costs`; the billing-only route uses
 * `gcp_baseline` and has no `current_costs` at all, which silently dropped every
 * spend attribute on a run whose measured spend was $685M.
 */
const costContainer = (estimate) => estimate.current_costs ?? estimate.gcp_baseline ?? {};

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

  // Phase facts belong only on the phase event that produced them. Without this
  // guard a terminal RUN_COMPLETED re-derives the estimate attributes, because
  // the session-end path sets `phase` from the snapshot's current_phase — which
  // restated every cost attribute a second time and double-counted it in any
  // aggregation grouped by attribute.
  const phaseEvent = event.eventName === "PHASE_COMPLETED";

  if (phaseEvent && event.phase === "DISCOVER") {
    const inventory = spec ? readJson(join(dir, spec.inventory)) : null;
    const resources = Array.isArray(inventory) ? inventory : inventory?.resources;

    // App-code AI detection lands here and nowhere else. Reading it is what lets
    // an AI workload with no AI *resource* — the SDK called from application code
    // — report hasAi at all; without it a Gemini-only service read as hasAi:false.
    const aiProfile = readJson(join(dir, "ai-workload-profile.json"));
    const aiFromProfile = Array.isArray(aiProfile?.models)
      ? aiProfile.models.length > 0
      : (aiProfile?.summary?.total_models_detected ?? 0) > 0;

    if (Array.isArray(resources)) {
      // Range-bounded in the model; clamp rather than emit an invalid value.
      attributes.resourceCount = Math.min(resources.length, 10000);
      const types = resourceTypes(resources);
      attributes.hasDatabase = DB_TYPE.test(types);
      attributes.hasAi = AI_TYPE.test(types) || aiFromProfile;
    } else if (aiProfile) {
      // No Terraform, so no inventory and no resourceCount — but the AI signal is
      // still knowable, and it is the whole point of an app-code-only migration.
      attributes.hasAi = aiFromProfile;
    }
  }

  if (phaseEvent && event.phase === "CLARIFY") {
    const preferences = readJson(join(dir, "preferences.json"));
    const clarifyMode = mapEnum(CLARIFY_MODE, preferences?.metadata?.migration_type);
    if (clarifyMode) attributes.clarifyMode = clarifyMode;
  }

  if (phaseEvent && event.phase === "ESTIMATE") {
    const estimates = readEstimates(dir);

    for (const estimate of estimates) {
      if (!attributes.recommendationOutcome) {
        const outcome = mapEnum(RECOMMENDATION_OUTCOME, estimate.recommendation?.outcome);
        if (outcome) attributes.recommendationOutcome = outcome;
      }
      if (!attributes.pricingSource) {
        const pricing = toPricingSource(
          estimate.pricing_source ?? estimate.projected_costs?.pricing_source,
        );
        if (pricing) attributes.pricingSource = pricing;
      }
    }

    // spendBand and spendBasis are emitted as a PAIR, from the same container.
    //
    // A band without a basis is the one combination that actively misleads: a
    // defaulted placeholder the artifact itself called "±100%+, not a
    // measurement" was published as FROM_100_TO_1K, indistinguishable from a
    // measured figure. So an unrecognised `source` now suppresses the number too,
    // rather than shipping it unqualified. A basis with no band is harmless —
    // there is no figure to misread — so it is still reported on its own.
    for (const estimate of estimates) {
      const container = costContainer(estimate);
      const basis = mapEnum(SPEND_BASIS, container.source);
      let band;
      for (const key of SOURCE_SPEND_KEYS) {
        band = toSpendBand(container[key]);
        if (band) break;
      }
      if (basis && band) {
        attributes.spendBand = band;
        attributes.spendBasis = basis;
        break;
      }
      if (basis && !attributes.spendBasis) attributes.spendBasis = basis;
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

/**
 * Per-invocation trigger trace.
 *
 * Counting emitted events cannot distinguish "the hook ran and correctly had
 * nothing to say" from "the hook never ran at all" — and those call for opposite
 * fixes. This records one line per process launch with the point it exited, so
 * triggers and endpoint calls can be reconciled separately. Debug-gated and
 * wrapped in try/catch, so it cannot affect the fail-open contract.
 */
const trace = { mode: "unknown", outcome: "unset", posted: 0, detail: undefined };

const writeTrace = () => {
  if (process.env.AWS_STARTUP_ADVISOR_TELEMETRY_DEBUG !== "1") return;
  try {
    const p = join(stateDir(), "trace.jsonl");
    mkdirSync(dirname(p), { recursive: true });
    appendFileSync(p, `${JSON.stringify({ at: new Date().toISOString(), ...trace })}\n`);
  } catch {
    /* ignore */
  }
};

// ------------------------------------------------------------- hook mode

/** Build and send one event. Shared by both hook modes so the envelope and the
 *  fail-open contract exist in exactly one place. */
/**
 * The model types sessionId as a UUID with a strict pattern, and a malformed
 * optional field is rejected at the request level — costing the whole event, not
 * just the field. sessionId is the only identifier we do not mint ourselves
 * (runId and installId come from randomUUID), so it is the only one that can
 * arrive in an unexpected shape from a host we do not control. Same
 * unknown-means-omit rule the enums use: drop the field, keep the event.
 */
const UUID_RE = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;
const asUuid = (value) => (typeof value === "string" && UUID_RE.test(value) ? value : undefined);

/**
 * The three payload fields whose names differ by host, read with fallbacks so one
 * script serves both without branching on which host it is.
 *
 * Claude Code sends `session_id` on every hook. Cursor sends it only on
 * sessionStart/sessionEnd; its tool, file and stop hooks carry `conversation_id`
 * instead, so without this fallback sessionId would be silently absent from every
 * Cursor event — the UUID gate would drop it and sittings-per-run would be
 * uncomputable for that host.
 */
const sessionOf = (hook) => hook?.session_id ?? hook?.conversation_id;

/** Cursor's file hooks carry no `cwd`; `workspace_roots` is the documented
 *  equivalent. process.cwd() remains the last resort for both hosts. */
const cwdOf = (hook) =>
  hook?.cwd ?? (Array.isArray(hook?.workspace_roots) ? hook.workspace_roots[0] : undefined) ?? process.cwd();

/** Claude Code puts the edited path under `tool_input.file_path`. Cursor's
 *  afterFileEdit puts it at the top level; its Write tool_input shape is not
 *  documented, so the known spellings are all accepted rather than guessed at. */
const filePathOf = (hook) =>
  hook?.tool_input?.file_path ??
  hook?.file_path ??
  hook?.tool_input?.target_file ??
  hook?.tool_input?.path;

const send = async (installId, skill, runId, event, dir, sessionId) => {
  const { runMode, ...rest } = event;
  const attributes = deriveAttributes(dir, skill, event) ?? {};
  if (runMode) attributes.runMode = runMode;

  const body = {
    installId,
    source: SOURCE,
    pluginVersion: pluginVersion(),
    occurredAt: Date.now(),
    // Fresh per emission: a genuine phase re-run is a real second occurrence
    // and must not dedup away.
    eventId: randomUUID(),
    pluginTelemetryEvent: {
      migrationActivity: {
        ...rest,
        skill,
        runId,
        // runId is stable for the life of the migration and sessionId changes
        // every sitting, so "how many sittings did this run take" is
        // COUNT(DISTINCT sessionId) GROUP BY runId — and the phase on each
        // session's last event is where that sitting stopped. Neither is
        // recoverable from timestamps: real gaps *within* one sitting run to 21
        // minutes, which overlaps how soon a user can return in a new one.
        ...(asUuid(sessionId) ? { sessionId } : {}),
        ...(Object.keys(attributes).length ? { attributes } : {}),
      },
    },
  };

  const endpoint = process.env.AWS_STARTUP_ADVISOR_TELEMETRY_ENDPOINT;
  const status = endpoint ? await post(endpoint, body) : null;
  debugLog({ at: new Date().toISOString(), status, body });
};

/**
 * SessionEnd: a final reconcile for the runs this session touched.
 *
 * It deliberately does NOT report unfinished runs as abandoned.
 *
 * It used to. That was wrong, because abandonment is a claim about the future —
 * "they never came back" — and session end cannot observe the future. It only
 * observes that this session stopped, which is a different fact. A customer who
 * reaches Estimate, quits, and finishes the same run dir three days later is the
 * normal case, not an edge case: the skill is built to resume, keeping one
 * `.migration/<id>/` dir across sessions.
 *
 * Emitting ABORTED at session end produced two terminal events for one runId in
 * exactly that case — ABORTED on day one, SUCCESS on day four — with phase events
 * arriving after the terminal. The rubric requires exactly one terminal per run,
 * and any consumer treating RUN_COMPLETED as end-of-stream mishandled it.
 *
 * Abandonment is knowable only where time is observable, which is the backend:
 * a runId with RUN_STARTED, no RUN_COMPLETED, and no activity for N days. runId
 * is carried across sessions (taken from the snapshot, never re-minted), so that
 * correlation is available downstream. This hook therefore emits only what it can
 * actually see — any transition written after the last Stop — which makes it a
 * cheap safety net rather than a guess.
 */
const runSessionEnd = async () => {
  trace.mode = "session_end";
  const hook = JSON.parse(readFileSync(0, "utf8"));
  const sessionId = sessionOf(hook);
  if (!sessionId) {
    trace.outcome = "no_session_id";
    return;
  }

  // Consent is resolved against the migration tree in the session's cwd, so the
  // payload has to be parsed before the check rather than after.
  const consent = readConsentAt(findMigrationRoot(cwdOf(hook)));
  if (consent.consent !== "granted" || optedOutByEnv()) {
    trace.outcome = "no_consent";
    return;
  }

  // Run dirs are discovered from cwd, then each one's co-located snapshot says
  // whether this session touched it and which skill owns it — which is why this
  // mode still needs no --skill argument and can stay registered at plugin level.
  let posted = 0;
  let seen = 0;
  for (const statusFile of findStatusFiles(cwdOf(hook))) {
    const runDir = dirname(statusFile);
    const snapshot = readJson(runPath(runDir));
    if (!snapshot || snapshot.sessionId !== sessionId) continue;
    seen++;
    const result = await processStatusFile(
      snapshot.skill, statusFile, sessionId, consent.installId ?? installId(),
    );
    posted += result.posted;
  }

  trace.posted = posted;
  trace.outcome = !seen ? "no_run_this_session" : posted ? "reconciled" : "no_delta";
};

/**
 * Diff one `.phase-status.json` against its snapshot and send what changed.
 *
 * Shared by both hook modes so the diff, the runId rule and the snapshot format
 * exist once. Whoever wrote the file — Write, Edit, or a shell heredoc — is
 * irrelevant here: the state on disk is the input.
 */
const processStatusFile = async (skill, absolute, sessionId, installId) => {
  const current = readJson(absolute);
  if (!current?.migration_id) return { outcome: "no_migration_id", posted: 0 };

  // A second migration skill invoked in the same session leaves both skills'
  // hooks registered, so confirm this run belongs to the skill that registered
  // this hook before reporting anything under its name.
  const spec = SKILL_INVENTORY[skill];
  const ownDir = dirname(absolute);
  const other = Object.entries(SKILL_INVENTORY).find(([name]) => name !== skill)?.[1];
  if (spec && other && !existsSync(join(ownDir, spec.inventory)) && existsSync(join(ownDir, other.inventory))) {
    return { outcome: "not_our_skill", posted: 0 };
  }

  const snapshotPath = runPath(ownDir);
  const snapshot = readJson(snapshotPath);
  const events = diffToEvents(snapshot, current);

  // runId is minted here, not derived from migration_id: that marker is
  // MMDD-HHMM, so two customers starting in the same minute would otherwise
  // share a runId on a shared backend.
  const runId = snapshot?.runId ?? randomUUID();

  for (const event of events) {
    await send(installId, skill, runId, event, ownDir, sessionId);
  }

  writeJson(snapshotPath, {
    runId,
    migration_id: current.migration_id,
    current_phase: current.current_phase,
    run_mode: current.run_mode,
    phases: current.phases ?? {},
    // Recorded so SessionEnd can find runs this session left unfinished, and
    // report each under the right skill with its artifacts still readable.
    skill,
    dir: ownDir,
    sessionId,
    completed: events.some((e) => e.eventName === "RUN_COMPLETED") || snapshot?.completed === true,
  });

  return { outcome: events.length ? "emitted" : "no_delta", posted: events.length };
};

const runHook = async (skill) => {
  trace.mode = "post_tool_use";
  const raw = readFileSync(0, "utf8");
  const hook = JSON.parse(raw);

  const filePath = filePathOf(hook);
  if (!filePath || basename(filePath) !== ".phase-status.json") {
    trace.outcome = "not_phase_status";
    // Record the payload's key names (never their values) when no path could be
    // found at all. Cursor's Write tool_input shape is undocumented, so if this
    // host spells the path differently the trace is the only place that would
    // show it — otherwise it would look identical to a hook that correctly fired
    // on some other file.
    if (!filePath) {
      const keys = Object.keys(hook ?? {});
      const toolKeys = Object.keys(hook?.tool_input ?? {});
      trace.detail = `no_path keys=${keys.join(",")} tool_input=${toolKeys.join(",")}`;
    }
    return;
  }

  const absolute = filePath.startsWith("/") ? filePath : join(cwdOf(hook), filePath);

  const consent = readConsentAt(findMigrationRoot(dirname(absolute)));
  if (consent.consent !== "granted" || optedOutByEnv()) {
    trace.outcome = "no_consent";
    return;
  }

  const result = await processStatusFile(
    skill, absolute, sessionOf(hook), consent.installId ?? installId(),
  );
  trace.outcome = result.outcome;
  trace.posted = result.posted;
};

/**
 * Find every `.phase-status.json` this reconcile should consider.
 *
 * Two independent sources, because neither alone is sufficient:
 *
 *  - **Snapshots.** Each records the run dir it came from, so any run already
 *    seen is found regardless of where the session has since wandered.
 *  - **The filesystem, walking up from cwd.** Needed for the case that matters
 *    most — a run whose every write went through Bash, so no snapshot exists at
 *    all and the run is otherwise completely invisible.
 *
 * Walking up rather than just checking `cwd/.migration` is not defensive
 * padding: the skills routinely `cd` into `.migration/<id>/` to work on
 * artifacts with relative paths, and the Stop payload reports that as the
 * session cwd. Resolving only against cwd therefore finds nothing on exactly
 * the runs that need reconciling. Observed directly: an agent `cd`-ed to
 * `.migration/0830-1601` and the first version of this function reported
 * `no_migration_dir` while the file sat one level up.
 */
const findStatusFiles = (base) => {
  const found = new Set();

  // Filesystem walk is now the only discovery mechanism needed: the snapshot
  // lives beside the phase file, so finding one finds both. It used to also scan
  // a central snapshot index, which no longer exists.
  //
  let dir = base;
  for (let depth = 0; depth < 5; depth++) {
    // cwd may itself BE the run dir, which is the common case after a cd.
    const here = join(dir, ".phase-status.json");
    if (existsSync(here)) found.add(here);

    const migrationRoot = join(dir, ".migration");
    if (existsSync(migrationRoot)) {
      for (const entry of readdirSync(migrationRoot)) {
        const candidate = join(migrationRoot, entry, ".phase-status.json");
        if (existsSync(candidate)) found.add(candidate);
      }
    }
    const parent = dirname(dir);
    if (parent === dir) break; // reached /
    dir = parent;
  }

  return [...found];
};

/**
 * Stop: reconcile on-disk state against the snapshot.
 *
 * The Stop payload carries no `tool_input`, so the run directory is discovered
 * rather than handed over. Every candidate is processed: the skills are told to
 * keep one run dir but also told to cope with several, and snapshots are keyed
 * by `migration_id`, so handling all of them is correct and idempotent.
 */
const runReconcile = async (skill) => {
  trace.mode = "stop_reconcile";
  const hook = JSON.parse(readFileSync(0, "utf8"));

  const consent = readConsentAt(findMigrationRoot(cwdOf(hook)));
  if (consent.consent !== "granted" || optedOutByEnv()) {
    trace.outcome = "no_consent";
    return;
  }

  const base = cwdOf(hook);
  const candidates = findStatusFiles(base);
  if (!candidates.length) {
    trace.outcome = "no_status_file";
    trace.detail = `cwd=${base}`;
    return;
  }

  const outcomes = [];
  let posted = 0;
  for (const candidate of candidates) {
    const result = await processStatusFile(
      skill, candidate, sessionOf(hook), consent.installId ?? installId(),
    );
    outcomes.push(result.outcome);
    posted += result.posted;
  }

  trace.posted = posted;
  trace.outcome = posted ? "recovered" : "no_delta";
  trace.detail = `${candidates.length} status file(s)`;
};

// ------------------------------------------------------------------- main

const main = async () => {
  const args = process.argv.slice(2);

  if (args[0] === "consent") {
    const action = args[1] ?? "get";
    const root = findMigrationRoot(process.cwd());
    if (action === "grant") return console.log(JSON.stringify(setConsent(true, root)));
    if (action === "revoke") return console.log(JSON.stringify(setConsent(false, root)));
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

  if (args.includes("--session-end")) return runSessionEnd();

  const skillIndex = args.indexOf("--skill");
  const skill = skillIndex === -1 ? undefined : args[skillIndex + 1];
  if (!skill) {
    trace.outcome = "no_skill_arg"; // nothing we could attribute an event to
    return;
  }
  if (args.includes("--reconcile")) return runReconcile(skill);
  await runHook(skill);
};

// Fail-open is the whole contract: swallow everything and exit 0. The trace is
// written in `finally` so an invocation is recorded on every path, including the
// ones that threw — otherwise the accounting would quietly under-count failures.
main()
  .catch((err) => {
    trace.outcome = "threw";
    trace.detail = String(err?.message ?? err).slice(0, 200);
  })
  .finally(() => {
    writeTrace();
    process.exit(0);
  });
