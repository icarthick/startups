---
_phase: estimate
_title: "Estimate AWS Costs"
_requires_phase: design
_input:
  - preferences.json
  - aws-design.json
  - aws-design-billing.json
  - aws-design-ai.json
_knowledge:
  - { file: references/shared/pricing-cache.md }
_fragments:
  - _id: estimate-infra
    _trigger: { _when: "aws-design.json exists" }
    _file: phases/estimate/estimate-infra.md
  - _id: estimate-billing
    _trigger: { _when: "aws-design-billing.json exists AND aws-design.json does NOT exist (billing-only fallback)" }
    _file: phases/estimate/estimate-billing.md
  - _id: estimate-ai
    _trigger: { _when: "aws-design-ai.json exists" }
    _file: phases/estimate/estimate-ai.md
_assemble:
  _file: phases/estimate/estimate-assemble.md
_produces:
  - { file: estimation-infra.json, _when: "infra route active (aws-design.json exists)" }
  - { file: estimation-billing.json, _when: "billing-only route active (aws-design-billing.json exists, no aws-design.json)" }
  - { file: estimation-ai.json, _when: "AI route active (aws-design-ai.json exists)" }
_advances_to: plan
_re_entry_guard:
  _stale_if_completed: plan
  _stale_artifact: generation-infra.json
  _on_reentry: stop_unless_confirmed
  _on_confirm: reset_downstream_to_pending
_preconditions:
  - _check_phase_completed: design
    _on_failure: _halt_and_inform
  - _check_single_active_phase: true
    _on_failure: _halt_and_inform
  - _check_file_exists: preferences.json
    _on_failure: _unrecoverable
  - _validate_json: preferences.json
    _on_failure: _unrecoverable
  - _assert: "at least one design artifact exists (aws-design.json, aws-design-billing.json, or aws-design-ai.json); if none, Estimate cannot run"
    _on_failure: _unrecoverable
  - _validate_schema: aws-design.json
    _on_failure: _unrecoverable
_postconditions:
  - _assert: "at least one estimate route was active and produced its artifact: infra route -> estimation-infra.json; billing-only route -> estimation-billing.json; AI route -> estimation-ai.json. If no route is active, the phase must not complete"
    _on_failure: _halt_and_inform
  - _assert: "every active route produced valid JSON (each of estimation-infra.json / estimation-billing.json / estimation-ai.json that a triggered route was responsible for exists and parses)"
    _on_failure: _halt_and_inform
  - _validate_schema: estimation-infra.json
    _on_failure: _halt_and_inform
  - _validate_schema: estimation-billing.json
    _on_failure: _halt_and_inform
  - _validate_schema: estimation-ai.json
    _on_failure: _halt_and_inform
  - _assert: "if estimation-infra.json exists: recommendation.path is one of {migrate_optimized, migrate_phased, stay}; recommendation.path_label, recommendation.migrate_if, and recommendation.stay_if are non-empty"
    _on_failure: _halt_and_inform
  - _assert: "every service priced carries a pricing_source in {cached, live, cached_fallback, unavailable}; services with pricing_source unavailable are listed in services_with_missing_fallback and excluded from totals"
    _on_failure: _halt_and_inform
  - _assert: "estimate-infra and estimate-billing never both produced an artifact in the same run"
    _on_failure: _halt_and_inform
_forbids_files:
  - README.md
  - "*.txt"
  - "terraform/**"
  - MIGRATION_GUIDE.md
  - generation-infra.json
  - generation-ai.json
  - generation-billing.json
---

# Phase 4: Estimate AWS Costs (Orchestrator)

**Execute ALL steps in order. Do not skip or optimize.**

This phase is driven by the interpreter loop in `INTERPRETER.md`. The entry gate
(design completed, single active phase, preferences present + valid, ≥1 design
artifact), the `.phase-status.json` write, and the `HANDOFF_OK`/`GATE_FAIL` completion
gate are owned by the interpreter and this phase's frontmatter. The prose below is the
estimate **procedure** — pricing-mode setup (shared across routes) then the per-route
cost analysis. Each route is a fragment fired by its `_when` trigger and writes its
own conditional artifact (see `_produces`). Infra and billing-only are mutually
exclusive; AI runs independently.

## Step 0: Pricing Mode Selection

Before running any sub-estimate file, determine the pricing source.

### Step 0a: Load Pricing Cache

Read `shared/pricing-cache.md`. Check the `Last updated` date in the header:

- If <= 90 days old: **Cached prices are the primary source.** No MCP calls needed for services listed in the cache. Proceed to Step 1.
- If > 90 days old: Cache is stale. Attempt MCP (Step 0b) for fresh prices; use stale cache as fallback.

### Step 0b: MCP Availability Check (only if cache stale or service not listed)

Attempt to reach awspricing with **up to 2 retries** (3 total attempts):

1. **Attempt 1**: Call `get_pricing_service_codes()`
2. **If timeout/error**: Wait 1 second, retry (Attempt 2)
3. **If still fails**: Wait 2 seconds, retry (Attempt 3)
4. **If all 3 attempts fail**: Use cached prices with staleness warning

### Step 0c: MCP Preflight — Surface Status to User (ALWAYS run)

**Before any sub-estimate file runs**, display the pricing mode to the user so they know what to expect:

- **If cache ≤ 90 days and MCP not needed**: "Pricing source: cached (updated [date], ±5-25% accuracy). Live pricing API not required."
- **If cache > 90 days and MCP available**: "Pricing source: live API (awspricing MCP). Cache is stale ([date]) — using real-time pricing."
- **If cache > 90 days and MCP unavailable**: "⚠️ Pricing source: stale cache only (updated [date]). The awspricing MCP server is unreachable — ensure `uvx` is installed (`pip install uv` or `brew install uv`) and AWS credentials are configured. Proceeding with cached pricing; accuracy may be ±15-25% for AI models."
- **If cache ≤ 90 days but a required service is NOT in cache and MCP unavailable**: "⚠️ Some services not in pricing cache and MCP unreachable. Those services will show `pricing_source: unavailable` in the estimate."

This prevents silent failures — the user sees the pricing constraint upfront, not after 5 minutes of estimation work.

### Pricing Hierarchy

Each sub-estimate file uses this lookup order per service:

1. **`shared/pricing-cache.md`** (primary) — Cached prices (±5-25% accuracy). Set `pricing_source: "cached"`. Used first because it requires zero API calls and covers most common services.
2. **MCP API** (secondary) — Real-time pricing for services NOT in pricing-cache.md (±5-10% accuracy, more precise). Set `pricing_source: "live"`. Only called when the cache lacks the needed service or model. **Region note:** The `.mcp.json` sets `AWS_REGION=us-east-1` as the MCP server default, but each `get_pricing()` call accepts a `region` parameter that overrides it. Always pass the user's target region (from `preferences.json`) in MCP queries.
3. **Cache after MCP failure** — If MCP was attempted but failed (timeout, error), and the service IS in the cache, use the cached price. Set `pricing_source: "cached_fallback"`. This distinguishes intentional cache use from MCP failure recovery.
4. **Unavailable** — If a service is NOT in the cache AND MCP is unavailable, set `pricing_source: "unavailable"` for that service. Add the service to `services_with_missing_fallback` and display a warning to the user: "Pricing unavailable for [service] — not in cache and MCP unreachable. Exclude from totals or provide a manual estimate."

**`pricing_source` values summary:**

| Value               | Meaning                                                   |
| ------------------- | --------------------------------------------------------- |
| `"cached"`          | Found in pricing-cache.md (normal path)                   |
| `"live"`            | Retrieved from MCP API in real-time                       |
| `"cached_fallback"` | MCP was attempted but failed; fell back to cache          |
| `"unavailable"`     | Not in cache AND MCP failed; service excluded from totals |

If cache is > 90 days old and MCP is unavailable:

- Add warning: "Cached pricing data is >90 days old; accuracy may be significantly degraded"
- **Display to user**: Add visible warning with staleness notice

## Step 1: Run the Active Estimate Routes

The entry gate (design completed, single active phase, preferences present + valid, ≥1
design artifact) is enforced by this phase's `_preconditions` frontmatter per
`INTERPRETER.md` § Gate protocol; proceed once it passes. Run each route whose `_when`
trigger holds:

- **Infrastructure** (`estimate-infra.md`) — when `aws-design.json` exists. Writes
  `estimation-infra.json`.
- **Billing-only** (`estimate-billing.md`) — when `aws-design-billing.json` exists and
  `aws-design.json` does NOT (fallback). Writes `estimation-billing.json`.
- **AI** (`estimate-ai.md`) — when `aws-design-ai.json` exists. Writes
  `estimation-ai.json`. Runs independently of the infra/billing route; run it after
  the infra/billing estimate completes.

Each route uses the Pricing Hierarchy from Step 0 (cache primary, MCP secondary,
cached-fallback, unavailable).

## Step 2: Assemble and Validate

Load `references/phases/estimate/estimate-assemble.md` (the phase's assembler) and
follow it to enforce the route output gates (≥1 active route produced its artifact;
infra XOR billing; infra recommendation-block checks) and own the phase's
artifact-level contract.

## Reference Files

- `shared/pricing-cache.md` — Cached AWS + source provider pricing (±5-25%, primary source)

## Scope Boundary

**This phase covers financial analysis ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Changes to architecture mappings from the Design phase
- Execution timelines or migration schedules
- Terraform or IaC code generation
- Detailed migration procedures or runbooks
- Team staffing or resource allocation

**Your ONLY job: Show the financial picture of moving to AWS. Nothing else.**
