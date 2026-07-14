# Phase 4: Estimate AWS Costs (Orchestrator)

**Execute ALL steps in order. Do not skip or optimize.**

## Step 0: Pricing Mode Selection

Before running any sub-estimate file, establish the pricing source.

The pricing hierarchy is **MCP-first, cache-fallback**. For each AWS service in the design, price it
via the credential-free `awspricingfree` MCP FIRST; only fall back to the cache when the MCP
withholds a price (returns `unsupported`/`unpriceable`) or is unreachable. Do **NOT** open the cache
first.

### Step 0a: Establish the `awspricingfree` pricing loop (do this BEFORE any calculation)

`awspricingfree` is the primary source — it reproduces calculator.aws to the cent, credential-free
(no AWS account needed, which matters for pre-migration customers). Each sub-estimate file drives its
four tools per service:

1. **Resolve** the AWS service name to a `serviceKey` — `resolve_service({query})` (or
   `list_services({})` to browse when the ranked guess is ambiguous).
2. **Describe** it — `describe_service({serviceKey})` to learn the required/conditional input ids,
   dropdown/unit options, `unitParam`/`sizeParam` companion keys, and (for multi-model services)
   the `templateIndex`.
3. **Price** it — `price({serviceKey, region, inputs, templateIndex?})` where `region` is the FULL
   name (`"US East (N. Virginia)"`, not `us-east-1`) and `inputs` are keyed by the describe ids.
   Map the `aws_config` from `aws-design.json` onto those inputs; **you** supply the usage volumes
   (task counts, storage GB, request counts) — the tool never fabricates them.

Handle each `price` response:

| Response                                            | Action                                                                                  | `pricing_source` |
| --------------------------------------------------- | --------------------------------------------------------------------------------------- | ---------------- |
| `{status:"ok", monthlyCost}`                        | Use `monthlyCost`. Record the `trace`/`breakdown` if useful.                            | `"live_free"`    |
| `{status:"needs_input", missing}`                   | Supply the named ids from `aws_config` (or documented defaults) and RE-CALL `price`.    | — (retry)        |
| `{status:"pointer", subServices}`                   | Pick the correct sub-service key (e.g. DynamoDB on-demand) and re-call `price` with it. | — (retry)        |
| `{status:"unsupported"}` / `{status:"unpriceable"}` | The MCP does not model this service — fall back to the cache (Step 0b).                 | (see 0b)         |

Do NOT accept an `ok $0` as a real price unless you actually supplied usage inputs (the MCP's
vacuous-$0 guard returns `needs_input` for unconfigured services, but stay alert).

### Step 0b: Cache fallback (only for services the MCP does not model, or when MCP is unreachable)

When `awspricingfree` returns `unsupported`/`unpriceable` for a service, look it up in
`shared/pricing-cache.md` and use the cached rate. Set `pricing_source: "cached"`. If the MCP was
unreachable entirely (connection failure, not a fail-closed status), price ALL cache-covered
services from the file and set `pricing_source: "cached_fallback"`.

### Step 0c: Credentialed fallback (last resort)

Only if a service is in NEITHER `awspricingfree` NOR `pricing-cache.md`: attempt the credentialed
`awspricing` MCP (see the Pricing Recipes table in `estimate-infra.md`). This requires AWS
credentials and is rarely reached. Set `pricing_source: "live"`. If it too fails, set
`pricing_source: "unavailable"`, add the service to `services_with_missing_fallback`, and warn the
user.

### Step 0d: MCP Preflight — Surface Status to User (ALWAYS run)

**Before any sub-estimate file runs**, display the pricing mode to the user so they know what to
expect:

- **If `awspricingfree` reachable**: "Pricing source: awspricingfree (credential-free, matches calculator.aws to the cent for modeled services). Cache used only for services it doesn't model."
- **If `awspricingfree` unreachable**: "⚠️ Pricing source: cached (`pricing-cache.md`, updated [date], ±5-25% accuracy). The awspricingfree MCP is unreachable — ensure the server is built (`/Volumes/workplace/AWSPricingMCP/dist/mcp/server.js`) and registered in `.mcp.json`. Proceeding with cached pricing."
- **If a required service is in NEITHER the MCP nor the cache**: "⚠️ Some services are modeled by neither the MCP nor the cache and will show `pricing_source: unavailable` in the estimate."

This prevents silent failures — the user sees the pricing constraint upfront, not after 5 minutes of estimation work.

### Pricing Hierarchy

Each sub-estimate file uses this lookup order per service:

| Priority | Source                                         | Condition                                                | `pricing_source` value |
| -------- | ---------------------------------------------- | -------------------------------------------------------- | ---------------------- |
| 1        | `awspricingfree` MCP (`price` → `status:"ok"`) | Service is modeled by the MCP                            | `"live_free"`          |
| 2        | `shared/pricing-cache.md`                      | MCP returns `unsupported`/`unpriceable`; service in cache | `"cached"`             |
| 3        | `pricing-cache.md` after MCP unreachable       | MCP connection failed entirely; service IS in cache      | `"cached_fallback"`    |
| 4        | Credentialed `awspricing` MCP (`get_pricing`)  | Service in NEITHER awspricingfree NOR cache              | `"live"`               |
| 5        | Unavailable                                    | In none of the above                                     | `"unavailable"`        |

**`pricing_source` values summary:**

| Value               | Meaning                                                        |
| ------------------- | -------------------------------------------------------------- |
| `"live_free"`       | Priced by the credential-free awspricingfree MCP (primary path) |
| `"cached"`          | awspricingfree does not model it; found in pricing-cache.md    |
| `"cached_fallback"` | awspricingfree was unreachable; fell back to cache             |
| `"live"`            | Retrieved from the credentialed awspricing MCP API (last resort) |
| `"unavailable"`     | In none of the above; service excluded from totals             |

**AI model note:** Bedrock per-token model pricing is NOT modeled by `awspricingfree` (which covers
calculator.aws infrastructure services, not token rates). `estimate-ai.md` therefore prices Bedrock
models from `pricing-cache.md` (primary) with the credentialed `awspricing` MCP as fallback — the
MCP-first rule above applies to infrastructure services (`estimate-infra.md`).

## Step 1: Prerequisites

1. Read `$MIGRATION_DIR/.phase-status.json`. If missing, invalid, or `phases.clarify` is not exactly `"completed"`: **STOP**. Output: "Phase 2 (Clarify) not completed or phase state is missing/invalid. Complete Clarify before Estimate."
2. Read `$MIGRATION_DIR/preferences.json`. If missing: **STOP**. Output: "Phase 2 (Clarify) not completed. Run Phase 2 first."

Check which design artifacts exist in `$MIGRATION_DIR/`:

- `aws-design.json` (infrastructure design from IaC)
- `aws-design-ai.json` (AI workload design)
- `aws-design-billing.json` (billing-only design)

If **none** of these artifacts exist: **STOP**. Output: "No design artifacts found. Run Phase 3 (Design) first."

## Step 2: Routing Rules

### Infrastructure Estimate

IF `aws-design.json` exists:

> Load `estimate-infra.md`

Produces: `estimation-infra.json`

### Billing-Only Estimate

IF `aws-design-billing.json` exists AND `aws-design.json` does **NOT** exist:

> Load `estimate-billing.md`

Produces: `estimation-billing.json`

### AI Estimate

IF `aws-design-ai.json` exists:

> Load `estimate-ai.md`

Produces: `estimation-ai.json`

### Mutual Exclusion

- **estimate-infra** and **estimate-billing** never both run (billing-only is the fallback when no IaC exists).
- **estimate-ai** runs independently of either estimate-infra or estimate-billing (no shared state). Run it after the infra/billing estimate completes.

## Phase Completion

Before marking Estimate complete, enforce route output gates (fail closed):

1. Determine which estimate routes ran:
   - Infra route: `aws-design.json` exists
   - Billing-only route: `aws-design-billing.json` exists AND `aws-design.json` does NOT exist
   - AI route: `aws-design-ai.json` exists
2. Require at least one route to be active. If none active: STOP.
3. For each active route, require its expected artifact:
   - Infra route -> `estimation-infra.json`
   - Billing-only route -> `estimation-billing.json`
   - AI route -> `estimation-ai.json`
4. If any active route is missing its expected output: STOP and output: "Estimate route [name] did not produce required artifact(s). Re-run the failed sub-estimate before completing Phase 4."

## Completion Handoff Gate (Fail Closed)

Load `shared/handoff-gates.md`. **Re-read from disk** each active estimate artifact before checking.

**Re-entry guard:** If `generation-infra.json` (or sibling generation artifacts) exists and `phases.generate` is not `"pending"`: STOP unless the user explicitly confirms re-running Estimate. Emit `GATE_FAIL | phase=estimate | field=generation-infra.json | reason=stale_downstream`.

**Infra route additional checks** (when `estimation-infra.json` exists):

- `recommendation.path` ∈ `{migrate_optimized, migrate_phased, stay}`
- `recommendation.path_label` is non-empty
- `recommendation.migrate_if` and `recommendation.stay_if` are non-empty arrays

**On any FAIL:** Emit `GATE_FAIL | phase=estimate | field=<path> | reason=missing`. **Do NOT modify artifacts to pass the gate.** **Do NOT update `.phase-status.json`.** Tell the user to re-run `estimate-infra.md` Part 7 (recommendation block).

**On PASS:** Emit `HANDOFF_OK | phase=estimate | artifacts=<comma-separated active estimate files>`.

After `HANDOFF_OK`, use the Phase Status Update Protocol (read-merge-write) to update `.phase-status.json` — **in the same turn** as the output message below:

- Set `phases.estimate` to `"completed"`
- Set `current_phase` to `"generate"`

Output to user: "Cost estimation complete. Proceeding to Phase 5: Generate Migration Artifacts."

## Reference Files

- `shared/pricing-cache.md` — Cached AWS + source provider pricing (±5-25%, FALLBACK for services `awspricingfree` does not model + all Bedrock/AI model rates)

## Scope Boundary

**This phase covers financial analysis ONLY.**

**Cost labeling rule (applies to ALL sub-estimate files):** All dollar figures presented to the user in chat summaries, report tables, and metric boxes MUST be labeled as "estimated monthly costs" or prefixed with "Est." — never present raw dollar amounts as if they are exact. This includes the Present Summary output, migration report content, and any user-facing cost references.

FORBIDDEN — Do NOT include ANY of:

- Changes to architecture mappings from the Design phase
- Execution timelines or migration schedules
- Terraform or IaC code generation
- Detailed migration procedures or runbooks
- Team staffing or resource allocation

**Your ONLY job: Show the financial picture of moving to AWS. Nothing else.**
