---
name: heroku-to-aws
description: "Migrate workloads from Heroku to AWS. Triggers on: migrate from Heroku, Heroku to AWS, move off Heroku, migrate Heroku app, migrate Heroku Postgres to RDS, migrate Heroku Redis to ElastiCache, migrate Heroku Kafka to MSK, migrate dynos to Fargate, Heroku migration, move from Heroku to AWS, migrate Heroku Private Space, Heroku to ECS, Heroku to Fargate, leave Heroku, migrate off Heroku platform. Runs a 6-phase process: discover Heroku resources from Terraform files, Procfile/app.json, and optional billing exports, clarify migration requirements, design AWS architecture, estimate costs, generate migration artifacts, and collect optional feedback. Clarify must finish before Design, Estimate, or Generate. Uses a flat resource model (no clustering or dependency graphs) with deterministic mapping tables for core services (Dynos → Fargate, Postgres → RDS/Aurora, Redis → ElastiCache, Kafka → MSK) and a fast-path table for 13+ common add-ons. Cedar/Fir generation detection is detect-only in v1. Pipeline/Review Apps are detect-only. Do not use for: GCP or Azure migrations to AWS, AWS-to-Heroku reverse migration, general AWS architecture advice without migration intent, Heroku-to-Heroku refactoring, or multi-cloud deployments that do not involve migrating off Heroku."
---

# Heroku-to-AWS Migration Skill

## Philosophy

- **Full platform exit by default**: Heroku is in sustaining engineering (KTLO) — stability and support only, no new investment. Enterprise contracts are no longer sold to new customers. This skill assumes complete departure from Heroku (compute, data, and add-ons) within a user-defined window. Do not recommend indefinite continued use of Heroku.
- **No legacy-to-legacy**: Do not recommend Elastic Beanstalk or AWS App Runner (no longer accepting new customers as of April 2026) as migration targets. Fargate is the sole compute target. ECS Express Mode may be mentioned as an optional simplified deployment path (same underlying Fargate + ALB cost model).
- **Interim cutover is bounded**: If a user chooses data-first migration (database on AWS, app temporarily on Heroku), treat this as a bounded phase (weeks, not quarters). Require a target exit date and surface KTLO platform risk warnings.
- **Re-platform by default**: Select AWS services that match Heroku workload types (e.g., Dynos → Fargate, Heroku Postgres → RDS/Aurora, Heroku Redis → ElastiCache, Kafka → MSK).
- **Dev sizing unless specified**: Default to development-tier capacity (e.g., db.t4g.micro, single AZ). Upgrade only on user direction.
- **No human one-time migration costs**: Do not present human labor, professional services, or people-time work as dollar estimates or "one-time migration cost" budget categories. Vendor charges grounded in data (for example Heroku invoice line items in the infra estimate when billing exists) are allowed.
- **Terraform + repo as primary discovery**: Terraform files (`.tf` with `heroku_*` resources) and repo artifacts (Procfile, app.json) are the primary data sources for resource discovery. No Platform API calls in v1.
- **Flat resource model**: Heroku resources are organized per-app without dependency graphs or clustering. No topological sorting, typed edges, or cluster formation logic. Resources are processed as a flat list in input order.
- **Deterministic mappings**: Core services use fixed lookup tables (Dyno Type Table, Postgres Plan Table, Redis Plan Table, Kafka Plan Table). Common add-ons use the Fast-Path Table. Unknown add-ons hit the specialist gate.
- **DMS has Heroku constraints**: AWS DMS cannot perform continuous replication (CDC) with Heroku Postgres because Heroku does not grant the REPLICATION role. DMS is for one-time bulk migration with a cutover window only. The skill must surface this constraint when DMS is selected.

---

## Definitions

- **"Load"** = Read the file using the Read tool and follow its instructions. Do not summarize or skip sections.
- **`$MIGRATION_DIR`** = The run-specific directory under `.migration/` (e.g., `.migration/0315-1030/`). Set during Phase 1 (Discover).

---

## Context Loading Rules

Each phase loads reference files on demand. To keep per-turn context manageable and prevent instruction-following degradation:

- **Budget:** Each phase should load no more than ~800 lines of instructions (excluding user artifacts like JSON profiles and MCP tool results).
- **Conditional loading:** Reference files with trigger conditions MUST NOT be loaded unless the condition is met. Do not speculatively load files.
- **No duplication:** Mapping tables, pricing data, and shared warnings exist in one canonical file. Other files reference them; they do not copy them inline.
- **Progressive depth:** `phase_router` determines which sub-files to load based on `routes.json` triggers. Load only the returned files.

**Conditional reference files (load ONLY when condition is true):**

| File                                       | Condition                                                    |
| ------------------------------------------ | ------------------------------------------------------------ |
| `references/phases/clarify/clarify.md` Q11 | `heroku_generation == "fir"` detected in any inventory entry |

---

## Prerequisites

User must provide:

- **Terraform IaC** (REQUIRED): `.tf` files containing `heroku_*` resource types (primary and required discovery path)
- **Repo artifacts** (SUPPLEMENTARY): Procfile and/or app.json in the workspace (supplements Terraform with commands, buildpacks, and declared add-ons — cannot stand alone)
- **Billing data** (OPTIONAL): Heroku Dashboard invoices or Enterprise CSV billing exports (for cost comparison)

If no Terraform files with `heroku_*` resources are found, stop and ask user to provide Heroku Terraform files. Procfile and app.json alone are not sufficient for discovery.

**Note:** Platform API discovery is NOT supported in v1. No API token is required or used.

---

## State Machine

Phase orchestration is managed by the `engine` MCP server. On each turn:

1. **Check for existing runs:**

   ```
   migration_status(project_dir=<project root>)
   ```

   **If runs exist** (one or more), present options to the user:
   - `[A] Resume` — Continue the most recent run from its current phase
   - `[B] Start fresh` — Create a new migration run
   - `[C] Cancel` — Stop

   Wait for user choice before proceeding. Do NOT silently resume.

   **If no runs exist**, proceed to step 2.

2. **Initialize (if no run exists):**

   ```
   migration_init(project_dir=<project root>, skill="heroku-to-aws")
   ```

   This creates `.migration/[MMDD-HHMM]/` with `.gitignore` and initial `.phase-status.json`.

3. **Route the current phase:**

   ```
   phase_router(migration_dir=$MIGRATION_DIR, project_dir=<project root>, skill="heroku-to-aws")
   ```

   Returns the list of reference files to load for the current phase. Load and follow each file.

4. **Advance after phase work completes:**

   ```
   phase_advance(migration_dir=$MIGRATION_DIR, project_dir=<project root>, skill="heroku-to-aws")
   ```

   Validates that required artifacts exist (gate check). If gate passes, advances to next phase. If gate fails, reports missing artifacts — do not proceed.

5. **Reset (if user wants to re-run a phase):**

   ```
   phase_reset(migration_dir=$MIGRATION_DIR, from_phase=<phase>, skill="heroku-to-aws")
   ```

**Clarify is mandatory:** Do not load design, estimate, or generate phase files unless `phase_router` returns them (it enforces `requires_phase` gates). If the user asks to skip Clarify, refuse briefly, then load the clarify reference file.

### Handoff Gate Orchestration (Fail Closed)

1. **Single `$MIGRATION_DIR`**: Use one run directory for the entire migration.
2. **Re-read from disk**: Before each phase, read required artifacts from `$MIGRATION_DIR/`.
3. **Advance only via `phase_advance`**: Do not manually update `.phase-status.json`. The tool handles validation and advancement.
4. **On gate failure**: `phase_advance` returns `status: "gate_failed"` with `missing_artifacts`. Report to user in plain language. Do NOT modify artifacts to pass. Do NOT continue.
5. **Re-entry**: Use `phase_reset` for re-running earlier phases. Requires explicit user confirmation.

---

## State Management

Migration state lives in `$MIGRATION_DIR` (`.migration/[MMDD-HHMM]/`), created by `migration_init` and managed by engine tools.

The `.migration/` directory is automatically protected by a `.gitignore` file created during init.

---

## Phase Summary Table

| Phase        | Inputs                                                                                           | Outputs                                                  | Routed via `phase_router`                                              |
| ------------ | ------------------------------------------------------------------------------------------------ | -------------------------------------------------------- | ---------------------------------------------------------------------- |
| **Discover** | Terraform files with `heroku_*` resources, Procfile, app.json, and/or billing exports            | `heroku-resource-inventory.json`                         | `discover-terraform.md`, `discover-billing.md`, `discover-assemble.md` |
| **Clarify**  | `heroku-resource-inventory.json`                                                                 | `preferences.json`                                       | `clarify.md`                                                           |
| **Design**   | `heroku-resource-inventory.json`, `preferences.json`                                             | `aws-design.json`                                        | `design.md`                                                            |
| **Estimate** | `aws-design.json`, `preferences.json`, optional billing profile                                  | `estimation-infra.json`                                  | `estimate.md`                                                          |
| **Generate** | `aws-design.json`, `estimation-infra.json`, `preferences.json`, `heroku-resource-inventory.json` | `terraform/`, `MIGRATION_GUIDE.md`, `README.md`, scripts | `generate-terraform.md`, `generate-docs.md`, `generate-validate.md`    |
| **Feedback** | All existing migration artifacts                                                                 | `feedback.json`                                          | `feedback.md`                                                          |

---

## MCP Servers

**engine** (phase management, discovery, design, estimate, generate):

- Provides `migration_status`, `migration_init`, `phase_router`, `phase_advance`, `phase_reset` (orchestration)
- Provides `heroku_discover_terraform`, `heroku_discover_billing` (discovery)
- Provides `heroku_design` (design)
- Provides `heroku_estimate` (estimate)
- Provides `heroku_generate_terraform`, `heroku_generate_docs` (generate)
- Used at every phase boundary and for deterministic computation
- Routes are defined in `heroku-to-aws/routes.json` within the server's knowledge directory

**awspricing** (for cost estimation):

- Provides `get_pricing`, `get_pricing_service_codes`, `get_pricing_service_attributes` tools
- Only needed during Estimate phase. Discover and Design do not require it.
- Primary pricing source: engine tool's cached rates (±5-10% for infrastructure). awspricing MCP is secondary — used only for services not covered by the tool.

---

## Files in This Skill

```
heroku-to-aws/
├── SKILL.md                                    ← You are here (execution controller)
│
├── references/
│   ├── phases/
│   │   ├── discover/
│   │   │   ├── discover-terraform.md           # Terraform discovery (calls heroku_discover_terraform tool)
│   │   │   ├── discover-billing.md             # Billing data parsing (calls heroku_discover_billing tool)
│   │   │   └── discover-assemble.md            # Assembles heroku-resource-inventory.json
│   │   ├── clarify/
│   │   │   └── clarify.md                      # Phase 2: Adaptive questions (12–15, batched ≤5)
│   │   ├── design/
│   │   │   └── design.md                       # Phase 3: Calls heroku_design tool
│   │   ├── estimate/
│   │   │   └── estimate.md                     # Phase 4: Calls heroku_estimate tool
│   │   ├── generate/
│   │   │   ├── generate-terraform.md           # Calls heroku_generate_terraform tool
│   │   │   ├── generate-docs.md                # Calls heroku_generate_docs tool
│   │   │   └── generate-validate.md            # Cross-reference validation
│   │   └── feedback/
│   │       └── feedback.md                     # Phase 6: Feedback collection
│   │
│   └── shared/
│       └── schema-discover-heroku.md           # heroku-resource-inventory.json schema
```

| Condition                                                | Action                                                                                                                                                        |
| -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| No Terraform files with `heroku_*` resources found       | Stop. Output: "No Terraform files with heroku_* resources found. Heroku Terraform is required for discovery. Procfile and app.json alone are not sufficient." |
| `.phase-status.json` missing phase gate                  | Stop. Output: "Cannot enter Phase X: Phase Y-1 not completed. Start from Phase Y or resume Phase Y-1."                                                        |
| awspricing unavailable after 3 attempts                  | Display user warning about ±5-10% accuracy. Use cached pricing from engine tool. Add `pricing_source: "cached_fallback"` to `estimation-infra.json`.          |
| User skips questions or says "use defaults for the rest" | Apply documented defaults for remaining questions. Phase 2 completes either way.                                                                              |
| Dyno type not in Dyno Type Table                         | Reject mapping for that formation. Output: "Unsupported dyno type: {type}. Cannot map to Fargate."                                                            |
| Add-on not in Fast-Path Table                            | Mark as "Deferred — specialist engagement". No automated mapping produced.                                                                                    |

## Defaults

- **IaC output**: Terraform configurations, migration scripts, and documentation
- **Region**: `us-east-1` (unless user specifies otherwise)
- **Sizing**: Development tier (e.g., `db.t4g.micro` for databases, 0.5 CPU for Fargate)
- **Migration mode**: Adapts based on available inputs (Terraform primary, Procfile/app.json supplementary, billing optional)
- **Cost currency**: USD
- **Timeline assumption**: 2-16 weeks depending on migration complexity — small (2-6 weeks), medium (6-12 weeks), large (12-18 weeks). Classified by `heroku_estimate` tool.

## Workflow Execution

When invoked, the agent **MUST follow this exact sequence**:

1. **Load phase status**: Read `.phase-status.json` from `.migration/*/`.
   - If missing: Initialize for Phase 1 (Discover)
   - If exists: Determine current phase using deterministic rules in **State Machine**

2. **Determine phase to execute**:
   - If `current_phase` exists: execute that phase.
   - Otherwise execute the first non-completed phase in ordered list: discover → clarify → design → estimate → generate.
   - If all ordered phases are completed: migration is complete (with feedback finalization rule).

3. **Read phase reference**: Load the full reference file for the target phase.

4. **Execute ALL steps in order**: Follow every numbered step in the reference file. **Do not skip, optimize, or deviate.**

5. **Validate outputs**: `phase_advance` validates all required artifacts exist before advancing. Do not manually check gates.

6. **Advance phase**: Call `phase_advance` to validate outputs and advance to next phase. If gate fails, report missing artifacts and stop.

7. **Phase status is tool-managed**: `phase_advance` handles status updates atomically. Do not write `.phase-status.json` manually.

8. **Feedback and sharing checkpoints**: After Estimate completes, offer feedback and/or plan sharing. This runs **before** advancing to Generate.

   - **After Discover**: No prompt. Proceed directly to Clarify.

   - **After Estimate** (if `phases.feedback` is `"pending"`): Output to user:

     ```
     ─── Share Your Migration Plan ───

     This link encodes your migration profile for partner matching:
     ✓ Included: Clarify answers, estimated costs, recommendation path,
       detected Heroku services, resource names, and workload types.
     ✗ Excluded: Source code, local file paths, credentials, API tokens,
       config-var values, and environment secrets.

     The link uses a URL fragment (#) — no data is sent to any server
     when you click it. The landing page decodes everything client-side.

     [A] Send feedback & share plan
     [B] Send feedback only
     [C] No thanks, continue to Generate
     ```

     - If user picks **A** → Load `references/phases/feedback/feedback.md`, execute it. Then generate share link. Set `phases.feedback` to `"completed"`. Continue to Generate.
     - If user picks **B** → Load `references/phases/feedback/feedback.md`, execute it. Set `phases.feedback` to `"completed"`. Continue to Generate.
     - If user picks **C** → Set `phases.feedback` to `"completed"`. Continue to Generate.

   - **After Generate**: Share-only prompt (no feedback re-ask):

     ```
     ─── Share Your Completed Plan ───

     This link encodes your migration profile for partner matching:
     ✓ Included: Clarify answers, estimated costs, recommendation path,
       detected Heroku services, resource names, and workload types.
     ✗ Excluded: Source code, local file paths, credentials, API tokens,
       config-var values, and environment secrets.

     The link uses a URL fragment (#) — no data is sent to any server
     when you click it. The landing page decodes everything client-side.

     [A] Share completed plan
     [B] No thanks, finish
     ```

     - If user picks **A** → Generate share link. Mark migration complete.
     - If user picks **B** → Mark migration complete.
     - If `phases.feedback` is still `"pending"`, set it to `"completed"` regardless of choice.

9. **Display summary**: Show user what was accomplished, highlight next phase, or confirm migration completion.

**Critical constraint**: Agent must strictly adhere to the reference file's workflow. If unable to complete a step, stop and report the specific issue. Do not fabricate or infer data.
