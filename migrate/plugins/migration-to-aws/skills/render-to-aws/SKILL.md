---
name: render-to-aws
description: "Migrate workloads from Render.com to AWS. Triggers on: migrate from Render, Render to AWS, move off Render, migrate Render app, migrate Render Web Service to AWS, migrate Render Background Worker to ECS, migrate Render Cron Job to EventBridge, migrate Render Postgres to RDS, migrate Render Redis to ElastiCache, Render migration, move from Render to AWS, render-to-aws, leave Render, migrate off Render platform, what-if workshop, reprice Render migration, compare migration scenarios, workshop mode. Runs a 6-phase process: discover Render resources from render.yaml and optional live CLI capture (read-only, consent-gated), clarify migration requirements, design AWS architecture, estimate costs, generate migration artifacts, and collect optional feedback. After Estimate, an optional what-if workshop can reprice region/HA/compute/Graviton scenarios without re-discovery. Clarify must finish before Design, Estimate, or Generate. Uses a flat resource model (no clustering or dependency graphs) with deterministic mapping tables for core service types (Web Service → Elastic Beanstalk by default, Background Worker → Fargate, Cron Job → EventBridge Scheduler + Lambda, PostgreSQL → RDS/Aurora, Key Value/Redis → ElastiCache). Do not use for: GCP or Heroku migrations to AWS, AWS-to-Render reverse migration, general AWS architecture advice without migration intent, or multi-cloud deployments that do not involve migrating off Render."
---

# Render-to-AWS Migration Skill

## Philosophy

- **Full platform exit by default**: This skill assumes complete departure from Render (compute, data, and managed services) within a user-defined window. Do not recommend indefinite continued use of Render.
- **PaaS-to-PaaS by default, recommendation-shaped**: Elastic Beanstalk (Docker platform, AL2023) is the default compute target for Web Services because it preserves Render's managed platform model (source deployment, platform-managed environments, and lower operational burden than direct container orchestration). Clarify presents a per-service compute recommendation before asking for confirmation. Fargate is the override for direct container control and is used automatically for Background Workers (always) and Web Services where horizontal scaling is required. EventBridge Scheduler + Lambda is the default for Cron Jobs (short-duration, serverless). ECS Fargate Scheduled Tasks is the override for heavy cron jobs. EKS remains the override for teams with Kubernetes expertise.
- **Re-platform by default**: Select AWS services that match Render service types (e.g., Web Services → Elastic Beanstalk, Background Workers → Fargate, Cron Jobs → EventBridge + Lambda, PostgreSQL → RDS/Aurora, Key Value → ElastiCache).
- **Dev sizing unless specified**: Default to development-tier capacity (e.g., db.t4g.micro, single AZ). Upgrade only on user direction.
- **No human one-time migration costs**: Do not present human labor, professional services, or people-time work as dollar estimates or "one-time migration cost" budget categories.
- **render.yaml-first discovery, live capture optional**: The authoritative IaC source is `render.yaml` in the workspace. Optional live discovery via the Render CLI (`render services list --output json`, etc., read-only, consent-gated) supplements or replaces it when available. Never capture API key values.
- **Flat resource model**: Render resources are organized as a flat per-service list without dependency graphs or clustering. Resources are processed as a flat list in input order.
- **Deterministic mappings**: Core service types use fixed lookup tables (Web Service Sizing Table, Background Worker Table, Cron Job Table, Postgres Plan Table, Redis Plan Table).
- **What-if after Estimate**: After costs are computed, SAs can enter an optional what-if workshop sidebar (`references/phases/workshop/workshop.md`) to change region, HA, compute target, or CPU architecture (x86 vs Graviton), refresh Design + Estimate, and compare up to 5 priced scenarios — without re-running Discover. Region dollar deltas need awspricing MCP; without it, rates stay us-east-1-cache-based. Workshop arch defaults to **x86_64**.

---

## Definitions

- **"Load"** = Read the file using the Read tool and follow its instructions. Do not summarize or skip sections.
- **`$MIGRATION_DIR`** = The run-specific directory under `.migration/` (e.g., `.migration/0315-1030/`). Set during Phase 1 (Discover).

---

## Phase Structure (frontmatter)

Phase and unit files carry a YAML frontmatter block that declares how the phase is
composed — its inputs, the fragments it runs, the assembler that combines them,
what it produces, its gates, and what it requires/advances-to. The DSL interpreter
contract is the vendored `references/vendored/dsl/INTERPRETER.md`: it defines every
frontmatter key, the fragment/assembler model, and the interpreter loop. **Load it
first** (once, at the start of a migration), then execute a phase file's prose
body.

---

## Context Loading Rules

Each phase loads reference files on demand. To keep per-turn context manageable and prevent instruction-following degradation:

- **Budget:** Each phase should load no more than ~800 lines of instructions (excluding user artifacts like JSON profiles and MCP tool results).
- **Conditional loading:** Reference files with trigger conditions MUST NOT be loaded unless the condition is met. Do not speculatively load files.
- **No duplication:** Mapping tables, pricing data, and shared warnings exist in one canonical file. Other files reference them; they do not copy them inline.
- **Progressive depth:** Phase orchestrators contain short routing logic that points to detailed sub-files. Load the sub-file only when its path is selected.

---

## Execution

This skill is driven by the interpreter loop in `INTERPRETER.md` (§ The interpreter
loop): it reads `.phase-status.json`, determines the current phase, runs each
phase's `_preconditions` / fragments / `_assemble` / `_postconditions`, advances on
`HANDOFF_OK` via `_advances_to`, and validates state.

**Cold start (entry phase).** On a cold start — no `.migration/` run with a
`.phase-status.json` yet — begin at `references/phases/discover/discover.md`, this
skill's entry phase (the one carrying `_init: true`).

**Clarify is mandatory (render policy).** Do not skip Clarify or jump straight to
Design, Estimate, or Generate even if the user asks — there is no exception for
"quick" or "obvious" migrations. A `preferences.json` that was not produced by an
actual Clarify run does not count. If asked to skip, refuse briefly and run
Clarify.

---

## State Management

Migration state lives in `$MIGRATION_DIR` (`.migration/[MMDD-HHMM]/`), created on
the first phase and persisted across invocations. The state file is
`.phase-status.json`; its shape is defined by
`references/vendored/state/phase-status.schema.json`.

---

## MCP Servers

**awspricing** (for cost estimation):

- Provides `get_pricing`, `get_pricing_service_codes`, `get_pricing_service_attributes` tools
- Only needed during Estimate phase. Discover and Design do not require it.
- Primary pricing source: `references/vendored/pricing/aws-infra-pricing.json` (cached AWS infrastructure rates, ±5-10% for infrastructure). MCP is secondary — used only for services not found in the pricing file.

---

## Files in This Skill

```
render-to-aws/
├── SKILL.md                                    ← You are here (skill entry point)
│
├── references/
│   ├── phases/
│   │   ├── discover/
│   │   │   ├── discover.md                     # Phase 1: Discover orchestrator
│   │   │   ├── discover-render-yaml.md         # render.yaml discovery
│   │   │   ├── discover-live.md                # Live CLI capture (consent-gated)
│   │   │   └── discover-assemble.md            # Assembler
│   │   ├── clarify/
│   │   │   ├── clarify.md                      # Phase 2: Adaptive questions
│   │   │   ├── clarify-interview.md            # Question catalog
│   │   │   └── clarify-assemble.md             # Assembler
│   │   ├── design/
│   │   │   ├── design.md                       # Phase 3: Design orchestrator
│   │   │   └── design-mapping.md               # Mapping engine
│   │   ├── estimate/
│   │   │   ├── estimate.md                     # Phase 4: Cost projection
│   │   │   ├── estimate-cost-engine.md         # Cost engine fragment
│   │   │   └── estimate-assemble.md            # Assembler
│   │   ├── workshop/
│   │   │   ├── workshop.md                     # Sidebar: optional post-Estimate what-if
│   │   │   ├── workshop-sheet.md               # Assumption sheet knobs
│   │   │   ├── workshop-refresh.md             # Patch prefs → Design → Estimate → snapshot
│   │   │   ├── workshop-compare.md             # Side-by-side scenarios
│   │   │   └── workshop-assemble.md            # Resolve sidebar → return to Generate
│   │   ├── generate/
│   │   │   ├── generate.md                     # Phase 5: Generate orchestrator
│   │   │   ├── generate-terraform.md           # Terraform configurations
│   │   │   ├── generate-docs.md                # MIGRATION_GUIDE.md + README.md
│   │   │   ├── generate-report.md              # migration-report.html
│   │   │   └── generate-assemble.md            # Cross-artifact validator assembler
│   │   └── feedback/
│   │       ├── feedback.md                     # Phase 6: Feedback collection
│   │       ├── feedback-collect.md             # Collect fragment
│   │       └── feedback-assemble.md            # Assembler
│   │
│   └── shared/                                 # render-to-aws's own shared references
│       ├── README.md
│       ├── render-pricing-cache.md             # Render plan pricing (source-side baseline)
│       ├── schema-discover-render.md           # render-resource-inventory.json schema
│       └── schema-workshop-scenarios.md        # scenarios/ + preferences.workshop contract
│
├── knowledge/design/                          # design lookup DATA
│   ├── web-service-eb-sizing.json              # Render plan → Elastic Beanstalk EC2 instance
│   ├── web-service-fargate-sizing.json         # Render plan → Fargate CPU/memory
│   ├── worker-fargate-sizing.json              # Background Worker plan → Fargate sizing
│   ├── cron-lambda-sizing.json                 # Cron Job → Lambda memory/timeout
│   ├── postgres-rds-sizing.json                # Postgres plan → RDS/Aurora sizing
│   └── redis-elasticache-sizing.json           # Redis plan → ElastiCache sizing
```

| Condition                                                | Action                                                                                                                                                                    |
| -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `.phase-status.json` missing phase gate                  | Stop. Output: "Cannot enter Phase X: Phase Y-1 not completed. Start from Phase Y or resume Phase Y-1."                                                                    |
| awspricing unavailable after 3 attempts                  | Display user warning about ±5-10% accuracy. Use `references/vendored/pricing/aws-infra-pricing.json`. Add `pricing_source: "cached_fallback"` to `estimation-infra.json`. |
| User skips questions or says "use defaults for the rest" | Apply documented defaults for remaining questions. Phase 2 completes either way.                                                                                          |
| Render service type not in selected compute sizing table | Reject mapping for that service. Output: "Unsupported service instance: {type}. Cannot map to target compute service."                                                    |

## Defaults

- **IaC output**: Terraform configurations, migration scripts, and documentation
- **Region**: `us-east-1` (unless user specifies otherwise)
- **Sizing**: Development tier (e.g., `db.t4g.micro` for databases, 0.5 CPU for Fargate)
- **Migration mode**: Adapts based on available inputs (render.yaml recommended, live CLI optional)
- **Cost currency**: USD
- **Timeline assumption**: 2-16 weeks depending on migration complexity — small (2-6 weeks), medium (6-12 weeks), large (12-18 weeks). Complexity tiers are classified per `references/vendored/estimate/complexity-tiers.json`.

## Feedback & Sharing Sidebars

The interpreter loop (`INTERPRETER.md` § The interpreter loop) drives phase
sequencing, gates, and state. This section defines only the render-specific
sidebar orchestration.

> **Plan-share links are GATED OFF.** The share landing page
> (`https://aws.amazon.com/startups/migrate/connect`) is not yet live (404). Do
> NOT offer, generate, or present a share link at any sidebar.

- **After Discover**: No prompt. Proceed directly to Clarify.

- **After Estimate**: First offer the what-if workshop sidebar per
  `estimate-assemble.md` (Enter workshop / Proceed toward Generate). Outer
  Estimate keeps `current_phase: estimate` until workshop is resolved (entered
  then exited via `workshop-assemble.md`, or declined). If the user enters
  workshop, follow `references/phases/workshop/workshop.md`. Then, if
  `phases.feedback` is `"pending"`:

  ```
  Would you like to share quick feedback? (5 optional questions +
  anonymized usage data — never resource names, file paths, or
  account IDs)

  [A] Yes, share feedback
  [B] No thanks, continue to Generate
  ```

  - If user picks **A** → Load `references/phases/feedback/feedback.md`, execute it. Set `phases.feedback` to `"completed"`. Continue to Generate.
  - If user picks **B** → Set `phases.feedback` to `"completed"`. Continue to Generate.

- **Workshop resume (mandatory):** If `current_phase == "estimate"` AND
  `phases.estimate == "completed"` AND `phases.workshop` is `"pending"` or
  `"in_progress"`, **do not recompute Estimate**. If `"pending"`, re-present the
  post-Estimate workshop offer from `estimate-assemble.md`. If `"in_progress"`,
  load `references/phases/workshop/workshop.md`. Generate must wait until
  `phases.workshop == "completed"` (entered+exited or declined).

- **Warm start / explicit what-if**: If the user says "what if", "reprice",
  "workshop mode", or "compare scenarios" and Estimate artifacts already exist,
  load `references/phases/workshop/workshop.md` directly.

- **After Generate**: No prompt. If `phases.feedback` is still `"pending"`, set it to `"completed"` and mark the migration complete.

**Critical constraint**: Follow each phase reference file's workflow exactly. If unable to complete a step, stop and report the specific issue. Do not fabricate or infer data.
