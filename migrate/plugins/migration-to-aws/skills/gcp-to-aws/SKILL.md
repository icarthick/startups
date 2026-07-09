---
name: gcp-to-aws
description: "Migrate workloads from Google Cloud Platform to AWS — including AI and agentic workloads regardless of cloud provider. Triggers on: migrate from GCP, GCP to AWS, move off Google Cloud, migrate Terraform to AWS, migrate Cloud SQL to RDS, migrate GKE to EKS, migrate Cloud Run to Fargate, Google Cloud migration, migrate from OpenAI to Bedrock, move off OpenAI, switch from ChatGPT API to AWS, migrate from Gemini to Bedrock, migrate LangChain to Bedrock, migrate LangGraph to AWS, migrate agentic workloads to AWS, move AI workloads to AWS, migrate my AI app to AWS. Runs a 7-phase process: discover GCP resources from Terraform files, app code, or billing exports, clarify migration requirements, design AWS architecture, estimate costs, plan the migration execution, generate migration artifacts, and collect optional feedback. Clarify must finish before Design, Estimate, Plan, or Generate. Includes AI provider migration guidance (for example, OpenAI to Amazon Bedrock) by selecting closest-fit Bedrock model families for required modality, latency/quality targets, context windows, and cost constraints. Model mapping is compatibility-guided, not 1:1 parity; validate prompts, tool-calling behavior, and eval metrics before cutover. Do not use for: Azure or on-premises migrations to AWS, AWS-to-GCP reverse migration, general AWS architecture advice without migration intent, GCP-to-GCP refactoring, or multi-cloud deployments that do not involve migrating off GCP."
---

# GCP-to-AWS Migration Skill

## Philosophy

- **Re-platform by default**: Select AWS services that match GCP workload types (e.g., Cloud Run → Fargate, Cloud SQL → RDS).
- **Dev sizing unless specified**: Default to development-tier capacity (e.g., db.t4g.micro, single AZ). Upgrade only on user direction.
- **No human one-time migration costs**: Do not present human labor, professional services, or people-time work as dollar estimates or "one-time migration cost" budget categories. Vendor charges grounded in data (for example GCP data transfer egress in the infra estimate when billing exists) are allowed.
- **Multi-signal approach**: Design phase adapts based on available inputs — Terraform IaC for infrastructure, billing data for service mapping, and app code for AI workload detection.
- **BigQuery / `google_bigquery_*`**: The skill **does not** recommend a specific AWS analytics or warehouse service. During **Clarify**, if discovery shows BigQuery (IaC `google_bigquery_*` and/or billing rows for BigQuery), you **must** surface the specialist advisory **before** Design (see `references/phases/clarify/clarify.md`). Design output uses **`Deferred — specialist engagement`**; keep directing the user to their **AWS account team** and/or a **data analytics migration partner** through Design, Estimate, and docs (see `references/phases/design/design-infra.md` BigQuery specialist gate).

---

## Definitions

- **"Load"** = Read the file using the Read tool and follow its instructions. Do not summarize or skip sections.
- **`$MIGRATION_DIR`** = The run-specific directory under `.migration/` (e.g., `.migration/0226-1430/`). Set during Phase 1 (Discover).

---

## Phase Structure (frontmatter)

Phase and unit files carry a YAML frontmatter block that declares how the phase is
composed — its inputs, the fragments it runs, the assembler that combines them, what it
produces, its gates, and what it requires/advances-to. The DSL interpreter contract is
the vendored `references/vendored/dsl/INTERPRETER.md`: it defines every frontmatter key, the
fragment/assembler model, and the interpreter loop. **Load it first** (once, at the
start of a migration), then execute a phase file's prose body. Elsewhere in this skill,
`INTERPRETER.md` (without a path) refers to this same loaded contract.

The backbone (discover → clarify → design → estimate → plan → generate → complete) is
wired by each phase's `_advances_to` / `_requires_phase`; `feedback` is an off-backbone
checkpoint. Design, Estimate, Plan, and Generate fan out into up to three routes
(infrastructure / AI / billing-only) via fragment `_when` triggers and conditional
`_produces` artifacts.

---

## Context Loading Rules

Each phase loads reference files on demand. To keep per-turn context manageable and prevent instruction-following degradation:

- **Budget:** Each phase should load no more than ~800 lines of instructions (excluding user artifacts like JSON profiles and MCP tool results).
- **Conditional loading:** Reference files with trigger conditions (e.g., `agentic_profile.is_agentic == true`) MUST NOT be loaded unless the condition is met. Do not speculatively load files.
- **No duplication:** Model mapping tables, pricing data, and shared warnings exist in one canonical file. Other files reference them; they do not copy them inline.
- **Progressive depth:** Phase orchestrators (`design.md`, `generate.md`) contain short routing logic that points to detailed sub-files. Load the sub-file only when its path is selected.

Each phase declares its own conditional reference/knowledge loads in frontmatter (a
fragment `_trigger` or a `_knowledge` entry's `_when`); do not maintain a separate
load-condition table here. The AI design-refs (`design-refs/ai-*-to-bedrock.md`, the
agentic `design-ref-*.md`, and `shared/retarget-gotchas.md`) are loaded conditionally
from within `design-ai.md` based on the detected `ai_source` and agentic
`migration_approach` — see that file for the exact conditions.

When adding new reference files, verify the phase's total loaded instructions remain under budget. If a new file would exceed ~800 lines when combined with other loaded refs, split it or make it conditional.

**Hybrid stack budget warning:**

When both `gcp-resource-inventory.json` AND `ai-workload-profile.json` exist, the combined design refs will approach the ~800-line budget. Output this warning to the user **before** loading the AI design refs:

> "⚠️ This is a large hybrid stack (infrastructure + AI workloads). To ensure complete and accurate recommendations, consider running the migration in two separate passes:
>
> **Pass 1 — Infrastructure:** Run with only your Terraform files to get infra mapping, Terraform generation, and cost estimates.
>
> **Pass 2 — AI workloads:** Run with only your application code to get Bedrock model recommendations, provider adapters, and AI migration artifacts.
>
> Continue with the combined run? (Y/N)"

If the user chooses to continue, proceed with the combined run. Load AI refs **after** infra refs to preserve infra instruction fidelity. If the user declines, stop and instruct them to re-run with a single input source type.

**This warning is advisory only** — it does not block the run.

---

## Prerequisites

User must provide at least one GCP source:

- **Terraform IaC**: `.tf` files (with optional `.tfvars`, `.tfstate`)
- **Application code**: Source files with GCP SDK or AI framework imports
- **Billing data**: GCP billing/cost/usage export files (CSV or JSON)

If none of the above are found, stop and ask user to provide at least one source type.

---

## Execution

This skill is driven by the interpreter loop in `INTERPRETER.md` (the plugin-shared
`references/vendored/dsl/INTERPRETER.md`): it reads `.phase-status.json`, determines the current
phase, runs each phase's `_preconditions` / fragments / `_assemble` / `_postconditions`,
advances on `HANDOFF_OK` via `_advances_to`, and validates state. **Load
`INTERPRETER.md` first** (once, at the start of a migration), then execute a phase
file's prose body. The phase set, ordering, and gates are all derived from the phase
files' frontmatter and `INTERPRETER.md` — they are not restated here.

**Cold start (entry phase).** On a cold start — no `.migration/` run with a
`.phase-status.json` yet — begin at `references/phases/discover/discover.md`, this
skill's entry phase (the one carrying `_init: true`). The interpreter loads THIS phase
directly; it does not scan every phase's frontmatter to find the root. All subsequent
phases are reached by following each phase's `_advances_to`. On a warm start,
`current_phase` in `.phase-status.json` is authoritative.

The backbone is a single linear chain:

```
discover (_init) → clarify → design → estimate → plan → generate → complete
                                                               ↖ feedback (checkpoint, off-backbone)
```

**Multi-route phases.** Design, Estimate, Plan, and Generate each fan out into up to three
routes (infrastructure / AI / billing-only), selected by which upstream artifacts
exist. Each route is a fragment fired by its `_when` trigger and writes its own
conditional artifact (see each phase's `_produces`). Multiple routes can run in one
migration (infra + AI is a common hybrid); infra and billing-only are mutually
exclusive. The route output gates ("≥1 route active, and each active route produced
its artifact") are enforced by each phase's assembler + `_postconditions`.

**Clarify is mandatory.** Do not skip Clarify or jump straight to Design, Estimate, or
Generate even if the user asks — there is no exception for "quick" or "obvious"
migrations. A `preferences.json` that was not produced by an actual Clarify run does
not count. A standalone **AI-only** flow (infrastructure stays on GCP; only AI/LLM
calls move to Bedrock) is a routing branch inside Clarify, not a separate entry point.

**BigQuery specialist gate.** If discovery shows BigQuery (`google_bigquery_*` in IaC
and/or BigQuery billing rows), Clarify must surface the specialist advisory before
Design, and Design/Estimate/docs must mark those resources **`Deferred — specialist
engagement`** (no Athena/Redshift/Glue/EMR recommendation). This is carried in the
phase prose + `_postconditions`.

---

## State Management

Migration state lives in `$MIGRATION_DIR` (`.migration/[MMDD-HHMM]/`), created on the
first phase (`discover`, which carries `_init: true`) and persisted across
invocations. The state file is `.phase-status.json`; how it is created, validated, and
updated across the lifecycle (the read-merge-write protocol, status values, single
active phase, re-entry guards) is defined in `INTERPRETER.md` § The interpreter loop.
The `.migration/` directory is protected by a `.gitignore` created at init.

---

## Phase Summary Table

| Phase        | Inputs                                                                                                                                                                   | Outputs                                                                                                                                                                                                                                       | Reference                                |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------- |
| **Discover** | `.tf` files, app source code, and/or billing exports (at least one required)                                                                                             | `gcp-resource-inventory.json`, `gcp-resource-clusters.json`, `ai-workload-profile.json`, `billing-profile.json`, `.phase-status.json` updated (outputs vary by input)                                                                         | `references/phases/discover/discover.md` |
| **Clarify**  | Discovery artifacts (`gcp-resource-inventory.json`, `gcp-resource-clusters.json`, `ai-workload-profile.json`, `billing-profile.json` — whichever exist)                  | `preferences.json`, `.phase-status.json` updated                                                                                                                                                                                              | `references/phases/clarify/clarify.md`   |
| **Design**   | `preferences.json` + discovery artifacts                                                                                                                                 | `aws-design.json` (infra), `aws-design-ai.json` (AI), `aws-design-billing.json` (billing-only)                                                                                                                                                | `references/phases/design/design.md`     |
| **Estimate** | `aws-design.json` or `aws-design-billing.json` or `aws-design-ai.json`, `preferences.json`                                                                               | `estimation-infra.json` or `estimation-ai.json` or `estimation-billing.json`, `.phase-status.json` updated                                                                                                                                    | `references/phases/estimate/estimate.md` |
| **Plan**     | `estimation-infra.json` or `estimation-ai.json` or `estimation-billing.json`, `aws-design*.json`, `preferences.json`                                                     | `generation-infra.json` or `generation-ai.json` or `generation-billing.json` (the execution plan), `.phase-status.json` updated                                                                                                              | `references/phases/plan/plan.md`         |
| **Generate** | `generation-infra.json` or `generation-ai.json` or `generation-billing.json`, `aws-design*.json`, `preferences.json`                                                     | `terraform/`, `scripts/`, `ai-migration/`, `validation-report.json` (when infra route active), `MIGRATION_GUIDE.md`, `README.md`, `migration-report.html`, `.phase-status.json` updated                                                       | `references/phases/generate/generate.md` |
| **Feedback** | `.phase-status.json` (discover completed minimum), all existing migration artifacts                                                                                      | `feedback.json`, `trace.json`, `.phase-status.json` updated                                                                                                                                                                                   | `references/phases/feedback/feedback.md` |

---

## MCP Servers

**awspricing** (for cost estimation):

- Provides `get_pricing`, `get_pricing_service_codes`, `get_pricing_service_attributes` tools
- Only needed during Estimate phase. Discover and Design do not require it.
- Primary pricing source: `references/shared/pricing-cache.md` (cached 2026 rates, ±5-10% for infrastructure, ±15-25% for AI models). MCP is secondary — used only for services not found in the cache.

---

## Files in This Skill

```
gcp-to-aws/
├── SKILL.md                                    ← You are here (skill entry point)
│
├── references/
│   ├── phases/                                 # ONLY declared units (phase / fragment / assembler)
│   │   ├── discover/
│   │   │   ├── discover.md                     # Phase 1: Discover orchestrator (_init entry)
│   │   │   ├── discover-iac.md                 # Fragment: Terraform/IaC discovery
│   │   │   ├── discover-app-code.md            # Fragment: App code discovery
│   │   │   ├── discover-billing.md             # Fragment: Billing discovery (full + lightweight modes)
│   │   │   └── discover-assemble.md            # Assembler: AI-profile merge + migration-preview
│   │   ├── clarify/
│   │   │   ├── clarify.md                      # Phase 2: Clarify orchestrator (thin)
│   │   │   ├── clarify-interview.md            # Fragment: full adaptive interview + AI-only routing
│   │   │   └── clarify-assemble.md             # Assembler: writes + validates preferences.json
│   │   ├── design/
│   │   │   ├── design.md                       # Phase 3: Design orchestrator (3-route)
│   │   │   ├── design-infra.md                 # Fragment: Infrastructure design (IaC-based)
│   │   │   ├── design-ai.md                    # Fragment: AI workload design (Bedrock)
│   │   │   ├── design-billing.md               # Fragment: Billing-only design (fallback)
│   │   │   └── design-assemble.md              # Assembler: route output gates
│   │   ├── estimate/
│   │   │   ├── estimate.md                     # Phase 4: Estimate orchestrator (3-route)
│   │   │   ├── estimate-infra.md               # Fragment: Infrastructure cost analysis
│   │   │   ├── estimate-ai.md                  # Fragment: AI workload cost analysis
│   │   │   ├── estimate-billing.md             # Fragment: Billing-only cost analysis
│   │   │   └── estimate-assemble.md            # Assembler: route + recommendation gates
│   │   ├── plan/
│   │   │   ├── plan.md                         # Phase 5: Plan orchestrator (3-route; execution plan JSON)
│   │   │   ├── plan-infra.md                   # Fragment: Infrastructure migration plan
│   │   │   ├── plan-ai.md                      # Fragment: AI migration plan
│   │   │   ├── plan-billing.md                 # Fragment: Billing-only migration plan
│   │   │   └── plan-assemble.md                # Assembler: route output gates
│   │   ├── generate/
│   │   │   ├── generate.md                     # Phase 6: Generate orchestrator (artifact fragments)
│   │   │   ├── generate-terraform.md           # Fragment: terraform/ (+ validation-report.json)
│   │   │   ├── generate-scripts.md             # Fragment: scripts/
│   │   │   ├── generate-ai-artifacts.md        # Fragment: ai-migration/ (adapters + test harness)
│   │   │   ├── generate-billing-skeleton.md    # Fragment: terraform/skeleton.tf
│   │   │   └── generate-assemble.md            # Assembler: docs + report + completion (reads all fragments)
│   │   └── feedback/
│   │       ├── feedback.md                     # Feedback checkpoint orchestrator (off-backbone)
│   │       ├── feedback-trace.md               # Fragment: anonymized trace builder
│   │       └── feedback-assemble.md            # Assembler: writes feedback.json, resolves checkpoint
│   │
│   ├── clarify-questions/                      # Question catalogs (reference data; read by clarify-interview)
│   │   ├── clarify-global.md                   # Category A: Global/Strategic (Q1-Q7)
│   │   ├── clarify-compute.md                  # Categories B+C: Config Gaps + Compute (Q8-Q11)
│   │   ├── clarify-database.md                 # Category D: Database (Q12–Q13b)
│   │   ├── clarify-ai.md                       # Categories F/G/H: AI/Bedrock, Agentic, Programs (Q14-Q27)
│   │   └── clarify-ai-only.md                  # Standalone AI-only migration flow
│   │
│   ├── discover/                               # Discover reference procedure (read by discover-assemble)
│   │   └── discover-preview.md                 # migration-preview.json heuristic (derives from artifacts)
│   │
│   ├── generate/                               # Generate reference procedure (read by generate-assemble)
│   │   ├── generate-docs.md                    # MIGRATION_GUIDE.md + README.md (reads all artifacts)
│   │   └── generate-report.md                  # migration-report.html (validates + reads all artifacts)
│   │
│   ├── design-refs/
│   │   ├── index.md                            # Lookup table: GCP type → design-ref file
│   │   ├── fast-path.md                        # Deterministic 1:1 mappings (Pass 1)
│   │   ├── compute.md                          # Compute mappings (Cloud Run, GCE, GKE, etc.)
│   │   ├── database.md                         # Database mappings (Cloud SQL, Spanner, etc.)
│   │   ├── storage.md                          # Storage mappings (GCS, Filestore, etc.)
│   │   ├── networking.md                       # Networking mappings (VPC, LB, DNS, etc.)
│   │   ├── messaging.md                        # Messaging mappings (Pub/Sub, etc.)
│   │   └── ai.md                               # AI mappings (Vertex AI → Bedrock)
│   │
│   ├── clustering/terraform/
│   │   ├── classification-rules.md             # Primary/secondary classification
│   │   ├── clustering-algorithm.md             # Cluster formation rules
│   │   ├── depth-calculation.md                # Topological depth calculation
│   │   └── typed-edges-strategy.md             # Edge type assignment
│   │
│   ├── shared/
│       ├── schema-discover-iac.md              # gcp-resource-inventory + clusters schemas
│       ├── schema-discover-ai.md               # ai-workload-profile schema
│       ├── schema-discover-billing.md          # billing-profile schema
│       ├── schema-estimate-infra.md            # estimation-infra.json schema
│       ├── validate-artifacts.md               # Pre-report validation (read-only)
│       ├── migration-complexity.md             # Complexity tier definitions (timeline scaling)
│       ├── pricing-cache.md                    # Cached AWS + source provider pricing (±5-25%)
│       └── bedrock-quotas.md                   # Bedrock TPM/RPM quota awareness + capacity planning
│   │
│   └── vendored/                               # DO NOT EDIT — synced copies of skills/shared/ (mise run shared:sync)
│       ├── dsl/INTERPRETER.md                  # the DSL interpreter contract (the program the LLM runs)
│       ├── estimate/complexity-tiers.json
│       ├── estimate/estimation-infra.schema.json
│       ├── pricing/aws-infra-pricing.json
│       └── state/phase-status.schema.json
```

| Condition                                                     | Action                                                                                                                                                  |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| No GCP sources found (no `.tf`, no app code, no billing data) | Stop. Output: "No GCP sources detected. Provide at least one source type (Terraform files, application code, or billing exports) and try again."        |
| awspricing unavailable after 3 attempts                       | Display user warning about ±5-25% accuracy. Use `pricing-cache.md`. Add `pricing_source: "cached_fallback"` to the applicable `estimation-*.json` file. |
| User skips questions or says "use defaults for the rest"      | Apply documented defaults for all remaining questions (essential questions and any unconfirmed sheet rows in wizard mode; current and subsequent batches in full mode). Q2/Q3 defaults add a report caveat. Phase 2 completes either way. |

## Defaults

- **IaC output**: Terraform configurations, migration scripts, AI migration code, and documentation
- **Region**: `us-east-1` (unless user specifies, or GCP region → AWS region mapping suggests otherwise)
- **Sizing**: Development tier (e.g., `db.t4g.micro` for databases, 0.5 CPU for Fargate)
- **Migration mode**: Adapts based on available inputs (infrastructure, AI, or billing-only)
- **Cost currency**: USD
- **Timeline assumption**: 2-16 weeks depending on migration complexity — small (2-6 weeks), medium (6-12 weeks), large (12-18 weeks). See `references/shared/migration-complexity.md` for tier definitions.

## Feedback Checkpoints

The interpreter loop (`INTERPRETER.md` § The interpreter loop) drives phase
sequencing, gates, and state. This section defines only the gcp-specific checkpoint
orchestration: WHERE the optional `feedback` checkpoint is offered (a checkpoint's
placement is orchestration prose, not part of the phase contract). Feedback is offered
at **two** interleaved checkpoints and is never a sequential backbone phase.

Marking `phases.feedback` `"completed"` means the checkpoint was **resolved** (offered
and dealt with), not that the user participated — participation is signalled by the
presence of `feedback.json`.

- **After Discover** (if `phases.feedback` is `"pending"`): Output to user:

  ```
  Would you like to share quick feedback (5 optional questions + anonymized usage
  data) to help improve this tool? Your data never includes resource names, file
  paths, or account IDs.
  [A] Send feedback now
  [B] Wait until after the Estimate phase
  ```

  - If user picks **A** → enter the `feedback` checkpoint (its `_trigger` is satisfied):
    load `references/phases/feedback/feedback.md`, execute it (this resolves the
    checkpoint), then continue to Clarify.
  - If user picks **B** → continue to Clarify. **Leave `phases.feedback` `"pending"`**
    so it can be re-offered after Estimate. Do NOT resolve the checkpoint here.

- **After Estimate** (if `phases.feedback` is `"pending"`): Output to user:

  ```
  Would you like to share quick feedback now? (5 optional questions + anonymized
  usage data)
  [A] Yes, share feedback
  [B] No thanks, continue to Generate
  ```

  - If user picks **A** → enter the `feedback` checkpoint: load
    `references/phases/feedback/feedback.md`, execute it, then continue to Generate.
  - If user picks **B** → resolve the checkpoint without participation: set
    `phases.feedback` to `"completed"`. Continue to Generate.

- **After Generate**: no feedback offer. If `phases.feedback` is still `"pending"`, set
  it to `"completed"` (the user had two chances and chose to defer/skip).

**Critical constraint**: Follow each phase reference file's workflow exactly. If unable
to complete a step, stop and report the specific step that failed. Do not fabricate or
infer data.

## Scope Notes

**v1.0 includes:**

- Terraform infrastructure discovery
- App code scanning (AI workload detection)
- Billing data import from GCP
- User requirement clarification (assumption-sheet wizard by default: confirm detected/assumed values, answer only essential questions; full adaptive question flow available on request)
- Multi-path Design (infrastructure, AI workloads, billing-only fallback)
- AWS cost estimation (from pricing API or fallback)
- Migration artifact generation (Terraform, scripts, AI adapters, documentation)
- Optional feedback collection with anonymized telemetry
