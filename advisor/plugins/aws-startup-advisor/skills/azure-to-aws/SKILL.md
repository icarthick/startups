---
name: azure-to-aws
description: "Migrate workloads from Azure to AWS using Terraform (azurerm provider). Triggers on: migrate from Azure to AWS, Azure to AWS migration, move from Azure to AWS, migrate Azure Terraform to AWS, migrate azurerm to AWS, Azure infrastructure migration, migrate azurerm_linux_web_app, migrate azurerm_postgresql_flexible_server, migrate azurerm_storage_account to S3, migrate azurerm_key_vault to Secrets Manager, Azure Terraform migration, migrate AKS to EKS, Azure workload migration, Azure IaC migration, migrate Azure Functions to Lambda, migrate Azure Redis to ElastiCache, migrate Azure VNet to VPC, migrate Azure container apps to ECS Fargate, azurerm to AWS Terraform. Scoped to Azure workloads defined in Terraform using the azurerm provider (.tf files, optional .tfvars/.tfstate). Runs a 5-phase process: discover Azure resources from Terraform files, clarify migration requirements, design AWS architecture, estimate costs, and generate migration artifacts (Terraform + MIGRATION_GUIDE.md + README.md). Uses a flat resource model with deterministic azurerm→AWS mapping tables. Do NOT use for: GCP or Heroku migrations (use gcp-to-aws or heroku-to-aws), non-Terraform Azure sources (ARM templates, Bicep, live CLI discovery), Azure AI/Azure OpenAI to Bedrock (use llm-to-bedrock), Azure DevOps or Entra ID migration, or general AWS architecture advice without migration intent."
---

# Azure-to-AWS Migration Skill (Terraform scope)

## Philosophy

- **Terraform-first in v1**: Input is Azure Terraform files using the `azurerm` provider (`.tf`,
  optional `.tfvars`/`.tfstate`). Non-Terraform Azure sources (ARM templates, Bicep, live
  CLI discovery) are out of scope in v1.
- **Flat resource model**: Azure resources are processed as a flat list using deterministic
  lookup tables — no dependency graphs or clustering. Resource entries are processed in input
  order.
- **ECS Fargate as default compute**: `azurerm_linux_web_app`/`azurerm_service_plan` and
  `azurerm_container_app` map to ECS Fargate by default. AWS App Runner is NOT a migration
  target (in maintenance, no new customers since April 30, 2026).
- **Detect-only gates for complex resources**: AKS (`azurerm_kubernetes_cluster`) and
  Cosmos DB (`azurerm_cosmosdb_*`) surface a specialist-gate recommendation instead of
  an automated mapping in v1.
- **Dev sizing unless specified**: Default to development-tier capacity (`db.t4g.micro`,
  single AZ). Upgrade only on user direction.
- **No human one-time migration costs**: Do not present labor, professional services, or
  people-time as dollar estimates. Vendor infrastructure charges grounded in data are allowed.

---

## Definitions

- **"Load"** = Read the file using the Read tool and follow its instructions. Do not
  summarize or skip sections.
- **`$MIGRATION_DIR`** = The run-specific directory under `.migration/` (e.g.,
  `.migration/0315-1030/`). Set during Phase 1 (Discover).

---

## Phase Structure (frontmatter)

Phase and unit files carry a YAML frontmatter block that declares how the phase is
composed — its inputs, the fragments it runs, the assembler that combines them, what it
produces, its gates, and what it requires/advances-to. The DSL interpreter contract is the
vendored `references/vendored/dsl/INTERPRETER.md`: it defines every frontmatter key, the
fragment/assembler model, and the interpreter loop. **Load it first** (once, at the start of
a migration), then execute a phase file's prose body.

---

## Context Loading Rules

Each phase loads reference files on demand. To keep per-turn context manageable:

- **Budget:** Each phase should load no more than ~800 lines of instructions (excluding user
  artifacts like JSON profiles and MCP tool results).
- **Conditional loading:** Reference files with trigger conditions MUST NOT be loaded unless
  the condition is met.
- **No duplication:** Mapping tables and pricing data exist in one canonical file.
- **Progressive depth:** Phase orchestrators contain short routing logic pointing to detailed
  sub-files. Load the sub-file only when its path is selected.

---

## Execution

This skill is driven by the interpreter loop in `INTERPRETER.md` (§ The interpreter loop):
it reads `.phase-status.json`, determines the current phase, runs each phase's
`_preconditions` / fragments / `_assemble` / `_postconditions`, advances on `HANDOFF_OK`
via `_advances_to`, and validates state.

**Cold start (entry phase).** On a cold start — no `.migration/` run with a
`.phase-status.json` yet — begin at `references/phases/discover/discover.md`, this
skill's entry phase (the one carrying `_init: true`). All subsequent phases are reached by
following each phase's `_advances_to`.

**Clarify is mandatory.** Do not skip Clarify or jump straight to Design, Estimate, or
Generate even if the user asks. If asked to skip, refuse briefly and run Clarify.

---

## State Management

Migration state lives in `$MIGRATION_DIR` (`.migration/[MMDD-HHMM]/`), created on the
first phase and persisted across invocations. The state file is `.phase-status.json`; its
shape is defined by `references/vendored/state/phase-status.schema.json`, and how it is
created, validated, and updated across the lifecycle is defined in `INTERPRETER.md`
§ The interpreter loop. The `.migration/` directory is protected by a `.gitignore`
created at init.

---

## MCP Servers

**awspricing** (for cost estimation):

- Provides `get_pricing`, `get_pricing_service_codes`, `get_pricing_service_attributes` tools
- Only needed during Estimate phase. Discover and Design do not require it.
- Primary pricing source: `references/vendored/pricing/aws-infra-pricing.json` (cached AWS
  infrastructure rates, ±5-10%). MCP is secondary — used only for services not in the cache.

---

## Files in This Skill

```
azure-to-aws/
├── SKILL.md                                    ← You are here (skill entry point)
│
├── references/
│   ├── phases/
│   │   ├── discover/
│   │   │   ├── discover.md                     # Phase 1: Discover orchestrator
│   │   │   ├── discover-terraform.md           # azurerm Terraform discovery
│   │   │   └── discover-assemble.md            # Discover assembler
│   │   ├── clarify/
│   │   │   ├── clarify.md                      # Phase 2: Clarify orchestrator
│   │   │   ├── clarify-interview.md            # Adaptive questions
│   │   │   └── clarify-assemble.md             # Clarify assembler
│   │   ├── design/
│   │   │   ├── design.md                       # Phase 3: Design orchestrator
│   │   │   ├── design-mapping.md               # azurerm → AWS mapping engine
│   │   │   └── design-assemble.md              # Design assembler
│   │   ├── estimate/
│   │   │   ├── estimate.md                     # Phase 4: Cost projection
│   │   │   ├── estimate-cost-engine.md         # Cost computation fragment
│   │   │   └── estimate-assemble.md            # Estimate assembler
│   │   ├── generate/
│   │   │   ├── generate.md                     # Phase 5: Generate orchestrator
│   │   │   ├── generate-terraform.md           # AWS Terraform generation
│   │   │   ├── generate-docs.md                # MIGRATION_GUIDE.md + README.md
│   │   │   └── generate-assemble.md            # Generate assembler
│   │   └── feedback/
│   │       ├── feedback.md                     # Optional feedback sidebar
│   │       ├── feedback-collect.md             # Feedback collection
│   │       └── feedback-assemble.md            # Feedback assembler
│   │
│   └── shared/                                 # azure-to-aws's own shared references
│       ├── README.md                           # what lives here + pointers
│       ├── azure-pricing-cache.md              # Azure resource pricing (source-side)
│       └── schema-discover-azure.md            # azure-resource-inventory.json schema
│
└── references/vendored/                        # synced from skills/shared/
    ├── README.md
    ├── dsl/INTERPRETER.md
    ├── pricing/aws-infra-pricing.json
    ├── state/phase-status.schema.json
    └── estimate/
        ├── complexity-tiers.json
        ├── estimation-infra.schema.json
        └── pricing-mode.md
```

| Condition                                                | Action                                                                                                                                                               |
| -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `.phase-status.json` missing phase gate                  | Stop. Output: "Cannot enter Phase X: Phase Y-1 not completed. Start from Phase Y or resume Phase Y-1."                                                               |
| awspricing unavailable after 3 attempts                  | Display warning about ±5-10% accuracy. Use `references/vendored/pricing/aws-infra-pricing.json`. Add `pricing_source: "cached_fallback"` to `estimation-infra.json`. |
| User skips questions or says "use defaults for the rest" | Apply documented defaults for remaining questions. Phase 2 completes either way.                                                                                     |
| azurerm resource type not in mapping table               | Mark as `"Specialist gate — defer"`. No automated mapping produced.                                                                                                  |

## Defaults

- **IaC output**: Terraform configurations and documentation
- **Region**: `us-east-1` (unless user specifies otherwise)
- **Sizing**: Development tier (`db.t4g.micro`, 0.5 vCPU / 1 GB for Fargate)
- **Cost currency**: USD
- **Timeline assumption**: 2-16 weeks depending on complexity — small (2-6 weeks), medium
  (6-12 weeks), large (12-18 weeks). Complexity tiers classified per
  `references/vendored/estimate/complexity-tiers.json`.

## Feedback Sidebar

The interpreter loop (`INTERPRETER.md` § The interpreter loop) drives phase sequencing,
gates, and state. This section defines only the azure-to-aws-specific sidebar placement.

> **Plan-share links are GATED OFF.** The share landing page
> (`https://aws.amazon.com/startups/migrate/connect`) is not yet live (404). Do NOT offer,
> generate, or present a share link at any sidebar.

- **After Estimate**: If `phases.feedback` is `"pending"`, offer:

  ```
  Would you like to share quick feedback? (5 optional questions +
  anonymized usage data — never resource names, file paths, or
  account IDs)

  [A] Yes, share feedback
  [B] No thanks, continue to Generate
  ```

  - If user picks **A** → Load `references/phases/feedback/feedback.md`, execute it. Set
    `phases.feedback` to `"completed"`. Continue to Generate.
  - If user picks **B** → Set `phases.feedback` to `"completed"`. Continue to Generate.

- **After Generate**: No prompt. If `phases.feedback` is still `"pending"`, set it to
  `"completed"` and mark the migration complete.

**Critical constraint**: Follow each phase reference file's workflow exactly. If unable to
complete a step, stop and report the specific issue. Do not fabricate or infer data.
