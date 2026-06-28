---
name: heroku-to-aws-dsl
description: "[DSL-refactor variant] Migrate workloads from Heroku to AWS, expressed as a declarative phase DSL the LLM interprets at runtime (no engine/server). Triggers on: migrate from Heroku, Heroku to AWS, move off Heroku, migrate Heroku Postgres to RDS, migrate Heroku Redis to ElastiCache, migrate Heroku Kafka to MSK, migrate dynos to Fargate. Runs a 6-phase process: discover, clarify, design, estimate, generate, feedback. Clarify must finish before Design/Estimate/Generate. Flat resource model (no clustering). Deterministic mapping tables for core services live in knowledge/ JSON. NOTE: this is the in-progress DSL-form rewrite of the heroku-to-aws skill; only the DISCOVER phase is authored + cold-LLM-validated so far. Do not use for: GCP/Azure migrations, AWS-to-Heroku reverse migration, general AWS architecture advice without migration intent."
---

# Heroku-to-AWS Migration Skill (DSL form)

This is the **declarative-DSL** rewrite of the `heroku-to-aws` skill. Instead of
phase logic living in long markdown orchestrators (or in an MCP engine), each
phase is a `*.phase.{yaml,md}` file that declares its structure — preconditions,
ordered steps, postconditions, cross-phase contracts — in a closed `_`-prefixed
vocabulary. **You (the LLM) are the interpreter.** There is no runtime engine.

## How to run this skill

1. **Read `INTERPRETER.md` ONCE.** It defines every `_`-key and the execution
   order (`_init` → `_preconditions` → load applicable `_knowledge` → `_steps` →
   `_postconditions` → advance per `_advances_to`). It is skill-agnostic and
   shared across every phase.
2. **Determine the current phase** from `$MIGRATION_DIR/.phase-status.json`
   (created by the discover phase's `_init`). If no `.migration/` run exists,
   start at discover. Otherwise pick the first phase whose status is not
   `"completed"` in the order: discover → clarify → design → estimate → generate.
3. **Load that phase's file from `phases/` and execute it** by following
   `INTERPRETER.md`. Each phase advances `.phase-status.json` ONLY after it emits
   `HANDOFF_OK`.

## Phase chain

| Phase    | File                        | Produces                          | Status |
| -------- | --------------------------- | --------------------------------- | ------ |
| Discover | `phases/discover.phase.md`  | `heroku-resource-inventory.json`  | ✅ authored + cold-LLM validated |
| Clarify  | `phases/clarify.phase.md`   | `preferences.json`                | ⏳ not yet ported |
| Design   | `phases/design.phase.md`    | `aws-design.json`                 | ⏳ not yet ported (arithmetic checkpoint) |
| Estimate | `phases/estimate.phase.md`  | `estimation-infra.json`           | ⏳ not yet ported |
| Generate | `phases/generate.phase.md`  | `terraform/`, guides, scripts     | ⏳ not yet ported |
| Feedback | `phases/feedback.phase.md`  | `feedback.json`                   | ⏳ not yet ported |

**Clarify is a mandatory gate** before Design/Estimate/Generate — enforced by
each downstream phase's `_requires_phase`, not by trust.

## Layout

```
heroku-to-aws-dsl/
├── SKILL.md                 ← you are here (entry point)
├── INTERPRETER.md           ← shared DSL interpreter — read first
├── phases/                  ← one *.phase.{yaml,md} per phase
│   └── discover/             ← a phase's route sub-units live in a dir named for it
│       ├── discover-terraform.md   (route: primary, required)
│       ├── discover-billing.md     (route: optional, glob-triggered)
│       └── discover-assemble.md    (route: always, merges contributions)
├── knowledge/               ← DATA only (JSON tables: dyno/pg/redis/kafka/...). NOT instructions.
│   └── design/              ← mapping tables as JSON (added when design is ported)
├── schemas/                 ← JSON Schemas — the cross-phase artifact contracts
├── fixtures/                ← test inputs for cold-LLM executability tests
└── test-output/             ← captured test artifacts + verdicts
```

A phase whose body is several triggered CONTRIBUTORS to one artifact (like
discover) declares them as `_routes` and authors each in `phases/<phase>/`. A
phase that is one linear sequence uses `_steps` inline. Note: route files hold
INSTRUCTIONS (`## Step:` sections); `knowledge/` holds DATA (lookup tables) —
these are different categories and live in different trees.

## Philosophy (unchanged from the markdown skill)

- Full platform exit by default; Fargate is the sole compute target (no Beanstalk
  / App Runner). EKS only when the user opts in via clarify.
- Re-platform mappings: Dynos → Fargate, Heroku Postgres → RDS/Aurora, Heroku
  Redis → ElastiCache, Kafka → MSK. Dev-tier sizing unless specified.
- Terraform + repo artifacts (Procfile/app.json) are the discovery sources; no
  Platform API calls in v1. Flat resource model — no clustering/dependency graphs.
- Deterministic mappings come from `knowledge/design/*.json` tables; the LLM does
  the lookup/clamp exactly as the table dictates (no improvisation).
- No human/one-time migration costs as dollar estimates.
