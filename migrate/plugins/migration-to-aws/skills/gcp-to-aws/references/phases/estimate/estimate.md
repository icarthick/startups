# Phase 4: Estimate AWS Costs (Orchestrator)

**Execute ALL steps in order. Do not skip or optimize.**

## Step 0: Pricing Mode Selection

Before running any sub-estimate file, establish the pricing source.

The **sole** pricing source is the credential-free `awspricingfree` MCP server. There is **NO cache
fallback and NO credentialed-API fallback** — every price comes from `awspricingfree`, or the
service is marked `unavailable` and excluded from totals. This is a deliberate constraint: the
estimate reflects exactly what the credential-free server can price, so it can be verified against
calculator.aws to the cent. Do **NOT** read `shared/pricing-cache.md` for infrastructure pricing,
and do **NOT** call the credentialed `awspricing` (`get_pricing`) MCP.

### Step 0a: Establish the `awspricingfree` pricing loop (do this BEFORE any calculation)

`awspricingfree` reproduces calculator.aws to the cent, credential-free (no AWS account needed, which
matters for pre-migration customers). Each sub-estimate file drives its four tools per service:

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
| `{status:"unsupported"}` / `{status:"unpriceable"}` | `awspricingfree` does not model this service. Mark it `unavailable` (Step 0b).          | `"unavailable"`  |

Do NOT accept an `ok $0` as a real price unless you actually supplied usage inputs (the MCP's
vacuous-$0 guard returns `needs_input` for unconfigured services, but stay alert).

#### Unit discipline (avoid orders-of-magnitude errors)

Request/count/rate inputs are the #1 source of wrong prices. Follow these rules:

1. **Always send the `__unit` companion for count/rate fields — never rely on the default.** Many
   request-count fields (SNS/SQS/EventBridge/Route 53/Lambda/DynamoDB/CodeArtifact) default to a
   SCALED unit (`millionPerMonth`, `thousandPerMonth`). A bare value is then silently multiplied:
   `numberOfRequests: 50000000` with no unit = 50,000,000 × 1,000,000 = **50 trillion/month**. Decide
   explicitly: send `{"numberOfRequests": 50, "numberOfRequests__unit": "millionPerMonth"}` for 50M,
   OR `{"numberOfRequests": 50000000, "numberOfRequests__unit": "perMonth"}` — both mean 50M.
2. **Read the field's `note` from `describe_service` before supplying it.** Scaled-unit fields carry
   an explicit "unit is REQUIRED / values are in MILLIONS" note naming the trap and the fix.
3. **`price` fails closed if you omit the unit on a scaled-default field** — a `needs_input` naming
   a `*__unit` id is the guard doing its job. Supply the unit; do NOT work around it by guessing.
4. **Sanity-check every returned magnitude.** A single commodity service (SNS/SQS/EventBridge/Lambda
   requests, NAT, ALB) priced in the thousands/millions of dollars/month is almost always a units
   mistake — re-read the field note and re-price before recording it. Likewise a suspiciously round
   or huge line in the `breakdown` (e.g. a silently-on add-on) deserves a second look.

### Step 0b: Unmodeled or unreachable → `unavailable` (NO fallback)

There is no fallback. Handle the two gaps explicitly:

- **Service not modeled** — when `awspricingfree` returns `unsupported`/`unpriceable` for a specific
  service call, set `pricing_source: "unavailable"`, add the service to
  `services_with_missing_fallback`, and EXCLUDE it from the tier totals. Surface it to the user as a
  known gap — do NOT substitute a cached or hardcoded rate.
- **MCP unreachable** — if `awspricingfree` cannot be reached at all (connection failure), the
  estimate cannot proceed. STOP and tell the user to build + register the server (see Step 0c). Do
  NOT silently fall back to cached pricing.

### Step 0c: MCP Preflight — Surface Status to User (ALWAYS run)

**Before any sub-estimate file runs**, confirm `awspricingfree` is reachable (a trivial
`resolve_service({query:"lambda"})` succeeds) and display the pricing mode:

- **If `awspricingfree` reachable**: "Pricing source: awspricingfree ONLY (credential-free, matches calculator.aws to the cent). Services it does not model are shown as `unavailable`, not substituted."
- **If `awspricingfree` unreachable**: "⚠️ STOP: the awspricingfree MCP is unreachable and there is no fallback. Build the server (`/workplace/carthick/AWSPricingMCP/dist/mcp/server.js`) and register it in `.mcp.json` before running Estimate." Do NOT proceed with cached pricing.
- **On any unmodeled service**: "⚠️ [service] is not modeled by awspricingfree — it will show `pricing_source: unavailable` and is excluded from the totals."

This prevents silent failures — the user sees the pricing constraint upfront, not after 5 minutes of estimation work.

### Pricing Hierarchy

There is exactly one source. No cache, no credentialed API.

| Priority | Source                                         | Condition                            | `pricing_source` value |
| -------- | ---------------------------------------------- | ------------------------------------ | ---------------------- |
| 1        | `awspricingfree` MCP (`price` → `status:"ok"`) | Service is modeled by the MCP        | `"live_free"`          |
| 2        | Unavailable                                    | `awspricingfree` does not model it   | `"unavailable"`        |

**`pricing_source` values summary:**

| Value           | Meaning                                                                    |
| --------------- | -------------------------------------------------------------------------- |
| `"live_free"`   | Priced by the credential-free awspricingfree MCP (the only pricing path)   |
| `"unavailable"` | awspricingfree does not model it; excluded from totals, surfaced as a gap  |

**AI model note:** Bedrock per-token model pricing is NOT modeled by `awspricingfree` (which covers
calculator.aws infrastructure services, not token rates). Under the awspricingfree-only rule,
Bedrock/AI model costs are therefore `unavailable` and excluded from the totals — `estimate-ai.md`
surfaces them as a known gap rather than substituting cached rates.

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

Produces: `estimation-infra.json` and diagnostic `pricing-attempts.json`

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
   - Infra route -> `estimation-infra.json` and `pricing-attempts.json`
   - Billing-only route -> `estimation-billing.json`
   - AI route -> `estimation-ai.json`
4. If any active route is missing its expected output: STOP and output: "Estimate route [name] did not produce required artifact(s). Re-run the failed sub-estimate before completing Phase 4."

## Completion Handoff Gate (Fail Closed)

Load `shared/handoff-gates.md`. **Re-read from disk** each active estimate artifact before checking.
For the infra route, also re-read `pricing-attempts.json`; it is a diagnostic sidecar, not a
user-facing report artifact.

**Re-entry guard:** If `generation-infra.json` (or sibling generation artifacts) exists and `phases.generate` is not `"pending"`: STOP unless the user explicitly confirms re-running Estimate. Emit `GATE_FAIL | phase=estimate | field=generation-infra.json | reason=stale_downstream`.

**Infra route additional checks** (when `estimation-infra.json` exists):

- `recommendation.path` ∈ `{migrate_optimized, migrate_phased, stay}`
- `recommendation.path_label` is non-empty
- `recommendation.migrate_if` and `recommendation.stay_if` are non-empty arrays
- `pricing-attempts.json` exists
- `pricing-attempts.json` root is an object with `phase`, `artifact`, `timestamp`, `pricing_tool`, `attempts`, and `summary`; a bare array is invalid
- Every priceable AWS service/component included in the estimate breakdown or exclusion list has a pricing attempt record
- Every attempt uses normalized terminal status: `priced`, `needs_usage`, `unavailable`, `not_priceable`, or `workflow_error`
- No attempt contains credentialed-pricing fields such as `mcp_tool: "get_pricing"`, `mcp_service_code`, `filters_used`, `price_monthly`, or `pricing_source: "manual"`; these violate the awspricingfree-only rule
- No attempt record has `terminal_status: "workflow_error"`; fix the retry workflow before completing Estimate

**On any FAIL:** Emit `GATE_FAIL | phase=estimate | field=<path> | reason=missing`. **Do NOT modify artifacts to pass the gate.** **Do NOT update `.phase-status.json`.** Tell the user to re-run `estimate-infra.md` Part 7 (recommendation block).

**On PASS:** Emit `HANDOFF_OK | phase=estimate | artifacts=<comma-separated active estimate files>`.

After `HANDOFF_OK`, use the Phase Status Update Protocol (read-merge-write) to update `.phase-status.json` — **in the same turn** as the output message below:

- Set `phases.estimate` to `"completed"`
- Set `current_phase` to `"generate"`

Output to user: "Cost estimation complete. Proceeding to Phase 5: Generate Migration Artifacts."

## Reference Files

- `shared/pricing-cache.md` — NOT used for pricing under the awspricingfree-only rule. (Retained in the skill for other phases; the Estimate phase does not read it.)

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
