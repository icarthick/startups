---
name: gcp-to-aws
description: "Migrate workloads from Google Cloud Platform to AWS — including AI and agentic workloads regardless of cloud provider. Triggers on: migrate from GCP, GCP to AWS, move off Google Cloud, migrate Terraform to AWS, migrate Cloud SQL to RDS, migrate GKE to EKS, migrate Cloud Run to Fargate, Google Cloud migration, migrate from OpenAI to Bedrock, move off OpenAI, switch from ChatGPT API to AWS, migrate from Gemini to Bedrock, migrate LangChain to Bedrock, migrate LangGraph to AWS, migrate agentic workloads to AWS, move AI workloads to AWS, migrate my AI app to AWS. Runs a 6-phase process: discover GCP resources from Terraform files, app code, or billing exports, clarify migration requirements, design AWS architecture, estimate costs, generate migration artifacts, and collect optional feedback. Clarify must finish before Design, Estimate, or Generate. Includes AI provider migration guidance (for example, OpenAI to Amazon Bedrock) by selecting closest-fit Bedrock model families for required modality, latency/quality targets, context windows, and cost constraints. Model mapping is compatibility-guided, not 1:1 parity; validate prompts, tool-calling behavior, and eval metrics before cutover. Do not use for: Azure or on-premises migrations to AWS, AWS-to-GCP reverse migration, general AWS architecture advice without migration intent, GCP-to-GCP refactoring, or multi-cloud deployments that do not involve migrating off GCP."
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

## Context Loading Rules

Each phase loads reference files on demand. To keep per-turn context manageable and prevent instruction-following degradation:

- **Budget:** Each phase should load no more than ~800 lines of instructions (excluding user artifacts like JSON profiles and MCP tool results).
- **Conditional loading:** Reference files with trigger conditions (e.g., `agentic_profile.is_agentic == true`) MUST NOT be loaded unless the condition is met. Do not speculatively load files.
- **No duplication:** Model mapping tables, pricing data, and shared warnings exist in one canonical file. Other files reference them; they do not copy them inline.
- **Progressive depth:** `phase_router` determines which sub-files to load based on `routes.json` triggers. The LLM loads only the returned files — no intermediate orchestrator files.

**Conditional reference files (load ONLY when condition is true):**

| File                                             | Condition                                                                                          |
| ------------------------------------------------ | -------------------------------------------------------------------------------------------------- |
| `design-refs/ai-gemini-to-bedrock.md`            | `ai-workload-profile.json` exists AND `summary.ai_source` = `"gemini"` or `"both"`                 |
| `design-refs/ai-openai-to-bedrock.md`            | `ai-workload-profile.json` exists AND `summary.ai_source` = `"openai"` or `"both"`                 |
| `design-refs/ai-anthropic-to-bedrock.md`         | `ai-workload-profile.json` exists AND `summary.ai_source` = `"anthropic"`                          |
| `design-refs/ai.md`                              | `ai-workload-profile.json` exists AND `summary.ai_source` = `"other"`                              |
| `design-refs/design-ref-harness.md`              | `agentic_profile.is_agentic == true` AND `ai_constraints.agentic.migration_approach == "harness"`  |
| `design-refs/design-ref-agentic-to-agentcore.md` | `agentic_profile.is_agentic == true` AND `ai_constraints.agentic.migration_approach == "strands"`  |
| `shared/retarget-gotchas.md`                     | `agentic_profile.is_agentic == true` AND `ai_constraints.agentic.migration_approach == "retarget"` |

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

Migration orchestration is handled by MCP tools. The agent follows this loop:

### Starting a migration

1. Call `migration_status(project_dir)`.
   - If existing runs found → present to user with phase status. Ask: Resume, Fresh, or Cancel.
   - If no runs → proceed to init.
2. Call `migration_init(project_dir)` if starting fresh.
3. Set `$MIGRATION_DIR` to the run directory returned.

### Phase execution loop

4. Call `phase_router(migration_dir, project_dir, skill="gcp-to-aws")`.
   - If error → stop and report (e.g., prerequisite phase not completed).
   - If `no_source_routes: true` → stop and show the tool's `message` to the user.
   - If `re_entry_warning` present → show warning to user, ask for confirmation.
     - If user confirms → call `phase_reset(migration_dir, project_dir, from_phase=current_phase)`, then proceed.
     - If user declines → stop.
   - Otherwise → load and execute each file in `routes[]` (in order).
5. Execute ALL steps in each loaded file. **Do not skip, optimize, or deviate.**
6. Call `phase_advance(migration_dir, project_dir, skill="gcp-to-aws")`.
   - If `gate_passed: true` → announce completion, check feedback checkpoint (see below).
   - If `gate_passed: false` → report missing artifacts. Do not advance.
7. Ask user: "Continue to [next phase]?"
   - If yes → repeat from step 4.
   - If no → stop. User can resume later.

### Feedback checkpoints

- **After Discover** (if feedback not yet collected): Ask user if they want to send feedback now or wait until after Estimate.
- **After Estimate** (if feedback still pending): Ask user one more time. If declined, mark feedback completed.
- **After Generate**: If feedback still pending, mark it completed (user had two chances).

### Critical constraints

- The agent must strictly follow each reference file's workflow. If unable to complete a step, stop and report the exact step that failed.
- `phase_advance` enforces fail-closed gates — all required artifacts must exist before advancing.
- Clarify is mandatory. `phase_router` will return an error if Design/Estimate/Generate are attempted before Clarify is completed.

---

## Phase Summary Table

| Phase        | Inputs                                                                                                                                                                   | Outputs                                                                                                                                                                                                                                       |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Discover** | `.tf` files, app source code, and/or billing exports (at least one required)                                                                                             | `gcp-resource-inventory.json`, `gcp-resource-clusters.json`, `ai-workload-profile.json`, `billing-profile.json`, `.phase-status.json` updated (outputs vary by input)                                                                         |
| **Clarify**  | Discovery artifacts (`gcp-resource-inventory.json`, `gcp-resource-clusters.json`, `ai-workload-profile.json`, `billing-profile.json` — whichever exist)                  | `preferences.json`, `.phase-status.json` updated                                                                                                                                                                                              |
| **Design**   | `preferences.json` + discovery artifacts                                                                                                                                 | `aws-design.json` (infra), `aws-design-ai.json` (AI), `aws-design-billing.json` (billing-only)                                                                                                                                                |
| **Estimate** | `aws-design.json` or `aws-design-billing.json` or `aws-design-ai.json`, `preferences.json`                                                                               | `estimation-infra.json` or `estimation-ai.json` or `estimation-billing.json`, `.phase-status.json` updated                                                                                                                                    |
| **Generate** | `estimation-infra.json` or `estimation-ai.json` or `estimation-billing.json`, `aws-design.json` or `aws-design-billing.json` or `aws-design-ai.json`, `preferences.json` | `generation-infra.json` or `generation-ai.json` or `generation-billing.json` + `terraform/`, `scripts/`, `ai-migration/`, `validation-report.json` (when infra route active), `MIGRATION_GUIDE.md`, `README.md`, `.phase-status.json` updated |
| **Feedback** | `.phase-status.json` (discover completed minimum), all existing migration artifacts                                                                                      | `feedback.json`, `trace.json`, `.phase-status.json` updated                                                                                                                                                                                   |

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
├── SKILL.md                                    ← You are here (orchestrator + state machine)
│
├── references/
│   ├── phases/
│   │   ├── discover/
│   │   │   ├── discover-iac.md                 # Terraform/IaC discovery
│   │   │   ├── discover-app-code.md            # App code discovery
│   │   │   ├── discover-billing.md             # Billing data discovery
│   │   │   └── discover-preview.md             # Migration preview
│   │   ├── clarify/
│   │   │   ├── clarify.md                     # Phase 2: Clarify orchestrator
│   │   │   ├── clarify-global.md              # Category A: Global/Strategic (Q1-Q7)
│   │   │   ├── clarify-compute.md             # Categories B+C: Config Gaps + Compute (Q8-Q11)
│   │   │   ├── clarify-database.md            # Category D: Database (Q12–Q13b)
│   │   │   ├── clarify-ai.md                  # Category F: AI/Bedrock (Q14-Q22)
│   │   │   └── clarify-ai-only.md             # Standalone AI-only migration flow
│   │   ├── design/
│   │   │   ├── design-infra.md                 # Infrastructure design (IaC-based)
│   │   │   ├── design-ai.md                    # AI workload design (Bedrock)
│   │   │   └── design-billing.md               # Billing-only design (fallback)
│   │   ├── estimate/
│   │   │   ├── estimate-infra.md               # Infrastructure cost analysis
│   │   │   ├── estimate-ai.md                  # AI workload cost analysis
│   │   │   └── estimate-billing.md             # Billing-only cost analysis
│   │   ├── generate/
│   │   │   ├── generate-infra.md               # Infrastructure migration plan
│   │   │   ├── generate-ai.md                  # AI migration plan
│   │   │   ├── generate-billing.md             # Billing-only migration plan
│   │   │   ├── generate-artifacts-infra.md     # Terraform configurations
│   │   │   ├── generate-artifacts-scripts.md  # Migration scripts
│   │   │   ├── generate-artifacts-ai.md        # Provider adapter + test harness
│   │   │   ├── generate-artifacts-billing.md   # Skeleton Terraform
│   │   │   └── generate-artifacts-docs.md      # MIGRATION_GUIDE.md + README.md
│   │   └── feedback/
│   │       ├── feedback.md                     # Phase 6: Feedback
│   │       └── feedback-trace.md               # Anonymized trace builder
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
│   └── shared/
│       ├── schema-phase-status.md              # .phase-status.json schema (canonical reference)
│       ├── schema-discover-iac.md              # gcp-resource-inventory + clusters schemas (loaded by discover-iac.md)
│       ├── schema-discover-ai.md               # ai-workload-profile schema (loaded by discover-app-code.md and discover-iac.md Step 7d)
│       ├── schema-discover-billing.md          # billing-profile schema (loaded by discover-billing.md)
│       ├── schema-estimate-infra.md            # estimation-infra.json schema (loaded by estimate-infra.md at write time)
│       ├── handoff-gates.md                    # Fail-closed phase handoff protocol (GATE_FAIL / HANDOFF_OK)
│       ├── validate-artifacts.md               # Pre-report validation (Generate Step 0; read-only)
│       ├── migration-complexity.md             # Complexity tier definitions (small/medium/large) for timeline scaling
│       ├── pricing-cache.md                    # Cached AWS + source provider pricing (±5-25%, primary source)
│       └── bedrock-quotas.md                   # Bedrock TPM/RPM quota awareness, burndown rates, capacity planning
```

| Condition                                                     | Action                                                                                                                                                  |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| No GCP sources found (no `.tf`, no app code, no billing data) | Stop. Output: "No GCP sources detected. Provide at least one source type (Terraform files, application code, or billing exports) and try again."        |
| `.phase-status.json` missing phase gate                       | Stop. Output: "Cannot enter Phase X: Phase Y-1 not completed. Start from Phase Y or resume Phase Y-1."                                                  |
| awspricing unavailable after 3 attempts                       | Display user warning about ±5-25% accuracy. Use `pricing-cache.md`. Add `pricing_source: "cached_fallback"` to the applicable `estimation-*.json` file. |
| User skips questions or says "use defaults for the rest"      | Apply documented defaults for remaining questions in the current batch and all subsequent batches. Phase 2 completes either way.                        |
| `aws-design.json` missing required clusters                   | Stop Phase 4. Output: "Re-run Phase 3 to generate missing cluster designs."                                                                             |

## Defaults

- **IaC output**: Terraform configurations, migration scripts, AI migration code, and documentation
- **Region**: `us-east-1` (unless user specifies, or GCP region → AWS region mapping suggests otherwise)
- **Sizing**: Development tier (e.g., `db.t4g.micro` for databases, 0.5 CPU for Fargate)
- **Migration mode**: Adapts based on available inputs (infrastructure, AI, or billing-only)
- **Cost currency**: USD
- **Timeline assumption**: 2-16 weeks depending on migration complexity — small (2-6 weeks), medium (6-12 weeks), large (12-18 weeks). See `references/shared/migration-complexity.md` for tier definitions.

## Workflow Notes

- User can invoke the skill again to resume — `migration_status` will show the current phase.
- `phase_router` returns the exact files to load. Do not manually determine which sub-files to read.
- `phase_advance` handles all status file updates atomically. Do not manually write `.phase-status.json`.
- If `phase_router` returns multiple routes, execute them in the order listed.

## Scope Notes

**v1.0 includes:**

- Terraform infrastructure discovery
- App code scanning (AI workload detection)
- Billing data import from GCP
- User requirement clarification (adaptive questions by category)
- Multi-path Design (infrastructure, AI workloads, billing-only fallback)
- AWS cost estimation (from pricing API or fallback)
- Migration artifact generation (Terraform, scripts, AI adapters, documentation)
- Optional feedback collection with anonymized telemetry
