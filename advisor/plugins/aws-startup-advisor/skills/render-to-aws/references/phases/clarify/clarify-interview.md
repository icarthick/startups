---
_fragment: interview
_of_phase: clarify
_contributes:
  - preferences.json (interpreted answers; created here, finalized by the assembler)
---

# Clarify Phase: Adaptive Interview

> Self-contained interview sub-file. Runs the prior-run check, determines fast-path
> eligibility, selects the active question set, and presents the questions in
> progressive batches — interpreting answers into `preferences.json` fields. The
> final assembly, validation checklist, handoff gate, and phase-status update are
> owned by the assembler (`clarify-assemble.md`).

**Execute ALL steps in order. Do not skip or deviate.**

---

## Step 0: Prior Run Check

Check `$MIGRATION_DIR/` for existing state:

**Case 1 — Completed preferences exist** (`preferences.json` present):

> "I found existing migration preferences from a previous run. Would you like to:"
>
> A) Re-use these preferences and skip questions
> B) Start fresh and re-answer all questions

- If A: Skip to Validation Checklist with the existing `preferences.json`.
- If B: Delete `preferences.json`, continue to Step 1.

**Case 2 — No prior state**: Continue to Step 1.

---

## Step 1: Read Inventory and Determine Fast-Path Eligibility

Read `$MIGRATION_DIR/render-resource-inventory.json`. This artifact must exist
(produced by Phase 1: Discover).

### Discovery Summary

Present a discovery summary:

> **Services discovered:** [total_services_discovered] Render services
> **Service types:** [count web_service] web, [count background_worker] worker, [count cron_job] cron, [count postgres] postgres, [count key_value] Redis
> **Out-of-scope (v1):** [count static_site + private_service if any — omit line if zero]
> **Discovery sources:** [render_yaml / live / render_yaml+live]

If `live_metadata.drift` is present:

> **Drift detected:** [services_live_only] services live-only, [services_render_yaml_only] in render.yaml only, [config_conflicts count] config conflicts.

### Fast-Path Gate

After the Discovery Summary, evaluate fast-path eligibility:

```
IF total_services_discovered < 5
   AND no service with service_type == "postgres" exists with config.high_availability == true
   AND no cron_job service exists
THEN eligible for fast-path (4–6 questions)
ELSE full question flow (10–12 questions)
```

**If fast-path eligible**, present:

> "Your stack looks straightforward — [N] service(s), no HA Postgres, no cron jobs.
>
> Want to use smart defaults and answer just 4–6 questions? I'll apply sensible defaults for the rest.
>
> **[Yes — short path]** / **[No — ask me everything]**"

**If user chooses Yes:**

1. Ask only: **Q1** (region), **Q2** (compliance), **Q3** (availability), **Q4** (maintenance window), **Q10** (DNS strategy).
2. If any `web_service` exists → also ask **Q9** (web compute target) and, if Q9 resolves to EB, **Q11** (EB deploy method).
3. Apply documented defaults for ALL other questions. Record each in `metadata.questions_defaulted`.
4. Write `preferences.json` with `metadata.clarify_mode: "fast_path"`. Skip Steps 2–3 batch loop.
5. Proceed to Step 4 (Validation Checklist).

**Fast-path default values applied when skipping questions:**

- `migration_urgency`: `routine`
- `migration_approach`: `full_cutover`
- `migration_method`: `pg_dump_restore`
- `database_ha`: matches Q3 availability
- `redis_ha`: `true`
- `cron_target`: `lambda` (if cron_job present; otherwise question not applicable)
- `dns_strategy`: `route53`
- `log_retention_days`: `30`
- `cost_optimization`: `balanced`
- `container_registry`: `ecr`

Users are informed: "Smart defaults applied: full cutover approach, pg_dump for database migration, Lambda for cron jobs, GitHub Actions for EB deploys. Say 'I want to change something' to override any of these."

**If user chooses No, or stack is not eligible:** Continue to Step 2.

---

## Step 2: Determine Active Questions

Before generating questions, scan the inventory to determine which questions apply:

### Conditional Question Rules

| Question                  | Condition to Include                            | Skip When                          |
| ------------------------- | ----------------------------------------------- | ---------------------------------- |
| Q1 — Target AWS region    | Always                                          | Never                              |
| Q2 — Compliance           | Always                                          | Never                              |
| Q3 — Availability posture | Always                                          | Never                              |
| Q4 — Maintenance window   | Always                                          | Never                              |
| Q5 — Environment naming   | Always                                          | Never                              |
| Q5b — Migration urgency   | Always                                          | Never                              |
| Q6 — Database HA          | postgres service present                        | No postgres in inventory           |
| Q6b — Migration approach  | postgres service present                        | No postgres in inventory           |
| Q6c — DB migration method | postgres service present                        | No postgres in inventory           |
| Q7 — Redis HA             | key_value service present                       | No key_value in inventory          |
| Q8 — Cron target          | cron_job service present                        | No cron_job in inventory           |
| Q9 — Web compute target   | web_service present                             | No web_service in inventory        |
| Q10 — DNS strategy        | Always                                          | Never                              |
| Q11 — EB deploy method    | Q9 resolved to `elastic_beanstalk` (or default) | No web_service, or all-Fargate web |
| Q12 — Container registry  | Always                                          | Never                              |
| Q13 — Log retention       | Always                                          | Never                              |
| Q14 — Alerting preference | Always                                          | Never                              |
| Q15 — Cost optimization   | Always                                          | Never                              |

### Batch Planning

After determining active questions, organize them into **three progressive batches**:

| Batch | Name               | Questions                 | Content                                                                                            |
| ----- | ------------------ | ------------------------- | -------------------------------------------------------------------------------------------------- |
| **1** | Global / Strategic | Q1–Q5, Q5b, Q9, Q11       | Region, compliance, availability, maintenance, environment naming, urgency, web compute, EB deploy |
| **2** | Data / Network     | Q6, Q6b, Q6c, Q7, Q8, Q10 | Database HA, migration approach, migration method, Redis HA, cron target, DNS strategy             |
| **3** | Operational        | Q12–Q15                   | Container registry, log retention, alerting, cost optimization                                     |

**Batch 2 is active** if ANY of: postgres present, key_value present, cron_job present (or DNS question is needed — always true → Batch 2 always fires with at least Q10).

**Batch 3 is always active** (Q12–Q15 always fire).

Record the ordered list of active batches and count questions per batch after filtering.

---

## Step 3: Present Questions in Progressive Batches

### Batch Loop

For each active batch, execute steps 3a–3c:

#### 3a. Present Batch

Use a conversational tone with brief context explaining why each question matters. Number questions within each batch starting from 1.

**Batch 1 — Global / Strategic (always first):**

```
Before designing your AWS architecture, I have a few sections of questions
to tailor the migration plan. You can answer each, skip individual ones
(I'll use sensible defaults), or say "use defaults for the rest" at any point.

Let's start with your strategic requirements.

--- Global / Strategic ---

[Present active questions Q1–Q5, Q5b, Q9, Q11]
```

**Batch 2 — Data / Network (if active):**

```
Got it — strategic preferences saved.

Next up: [N] questions about your data services and networking.
You can answer each, skip individual ones, or say "use defaults for the rest."

--- Data / Network ---

[Present active questions Q6–Q10]
```

**Batch 3 — Operational:**

```
[Data/Network preferences saved.]

Last section — [N] questions about operations and platform choices, then we're ready to design.
You can answer each, skip individual ones, or say "use defaults for the rest."

--- Operational ---

[Present active questions Q12–Q15]
```

#### 3b. Wait for Response

Wait for the user's response to the current batch. Do NOT present the next batch or proceed to Design without a response or an explicit "use defaults for the rest."

**"Use defaults for the rest" handling:** If the user says this at any point:

1. Apply documented defaults for all unanswered questions in the current batch.
2. Apply documented defaults for all questions in remaining batches.
3. Record each defaulted answer with `source: "default"`.
4. Skip directly to Step 4 (write final `preferences.json`).

#### 3c. Interpret Batch Answers and Validate

For each answered question, apply the interpretation rule. For skipped questions within the batch, apply the documented default.

**Input Validation:** If the user provides a response that does not match the valid options for a question:

1. Reject the input.
2. Present an error message indicating the valid options.
3. Re-prompt the same question without advancing.

Example:

> "That's not a valid option for [question topic]. Please choose from: [list valid options]"

---

## Question Catalog

### Batch 1: Global / Strategic

#### Q1 — Target AWS Region

> Which AWS region should your infrastructure be deployed to?
>
> A) us-east-1 (N. Virginia) — lowest latency to East Coast, most services available
> B) us-west-2 (Oregon) — West Coast; closest to Render's primary region (Oregon) (default)
> C) eu-west-1 (Ireland) — Europe, good for EU-based users
> D) eu-central-1 (Frankfurt) — Central Europe, German data residency
> E) ap-southeast-1 (Singapore) — Asia-Pacific
> F) ap-northeast-1 (Tokyo) — Japan
> G) Other — specify a valid AWS region code

**Interpret:**

- A → `target_region: "us-east-1"`
- B → `target_region: "us-west-2"`
- C → `target_region: "eu-west-1"`
- D → `target_region: "eu-central-1"`
- E → `target_region: "ap-southeast-1"`
- F → `target_region: "ap-northeast-1"`
- G → validate user-provided region code; `target_region: "<user value>"`

**Default:** B → `target_region: "us-west-2"` (Oregon, matching Render's default region)

**Valid options:** Any valid AWS region code. Reject non-existent region codes.

---

#### Q2 — Compliance Requirements

> Do you need to meet any compliance frameworks?
>
> A) None — no specific compliance requirements
> B) SOC 2 — service organization controls
> C) HIPAA — healthcare data protection
> D) PCI DSS — payment card data
> E) Multiple — specify which ones

**Interpret:**

- A → `compliance: "none"`
- B → `compliance: "soc2"`
- C → `compliance: "hipaa"`
- D → `compliance: "pci"`
- E → `compliance: [user-specified array]`

**Default:** A → `compliance: "none"`

**Design impact:** HIPAA → BAA-eligible services only; PCI → encryption at rest and in transit mandatory; SOC 2 → audit logging required.

---

#### Q3 — Availability Posture

> What availability level does your production workload need?
>
> A) Single-AZ — development/staging, cost-optimized (no redundancy)
> B) Multi-AZ — production standard (automatic failover within a region)
> C) Multi-AZ HA — mission-critical (Aurora, enhanced monitoring, aggressive failover)
> D) Multi-Region — catastrophic tolerance (global distribution, highest cost)

**Interpret:**

- A → `availability: "single-az"`
- B → `availability: "multi-az"`
- C → `availability: "multi-az-ha"`
- D → `availability: "multi-region"`

**Default:** B → `availability: "multi-az"`

**Design impact:**

- `single-az` or `multi-az` → RDS PostgreSQL
- `multi-az-ha` or `multi-region` → Aurora PostgreSQL

---

#### Q4 — Maintenance Window

> When should AWS perform maintenance operations (patches, minor upgrades)?
>
> A) Weekday off-hours (Tue–Thu, 02:00–06:00 UTC)
> B) Weekend early morning (Sat–Sun, 02:00–06:00 UTC)
> C) Sunday pre-dawn (Sun 03:00–05:00 UTC) — recommended
> D) Flexible — no preference, use AWS defaults

**Interpret:**

- A → `maintenance_window: {"day": "tuesday-thursday", "hour_utc": 3}`
- B → `maintenance_window: {"day": "saturday-sunday", "hour_utc": 3}`
- C → `maintenance_window: {"day": "sunday", "hour_utc": 4}`
- D → `maintenance_window: "flexible"`

**Default:** D → `maintenance_window: "flexible"`

---

#### Q5 — Environment Naming

> What should the primary environment be called in AWS resource naming and tags?
>
> A) production
> B) prod
> C) live
> D) Other — specify

**Interpret:**

- A → `environment_naming: "production"`
- B → `environment_naming: "prod"`
- C → `environment_naming: "live"`
- D → `environment_naming: "<user value>"`

**Default:** A → `environment_naming: "production"`

---

#### Q5b — Migration Urgency

> How urgent is this migration?
>
> A) Routine — no specific deadline, moving at your own pace
> B) Planned — target completion within a quarter, soft deadline
> C) Urgent — hard deadline (contract expiry, budget, compliance)

**Interpret:**

- A → `migration_urgency: "routine"`
- B → `migration_urgency: "planned"`
- C → `migration_urgency: "urgent"`

**Default:** A → `migration_urgency: "routine"`

---

#### Q9 — Web Service Compute Target

> _Fires only when `web_service` is present in the inventory._
>
> Based on your Render web services, I recommend **Elastic Beanstalk** as the default —
> it preserves the PaaS-managed model closest to Render's experience. Fargate is
> available if your team prefers direct container control.
>
> Which compute target should your web services use?
>
> A) Elastic Beanstalk (default) — managed PaaS platform, LoadBalanced environment with ALB
> B) ECS Fargate — direct container management, more operational flexibility
>
> Note: background_worker services ALWAYS map to Fargate (not configurable here).
> Note: cron_job services are handled separately (see the Cron Target question).

**Interpret:**

- A → `design_constraints.web_compute_target: "elastic_beanstalk"`
- B → `design_constraints.web_compute_target: "ecs-fargate"`

**Default:** A → `design_constraints.web_compute_target: "elastic_beanstalk"`

---

#### Q11 — Elastic Beanstalk Deployment Mechanism

> _Fires only when the web compute target resolves to Elastic Beanstalk (`design_constraints.web_compute_target` is `"elastic_beanstalk"` or absent, and web_service exists)._
>
> How do you want to deploy code changes to Elastic Beanstalk?
>
> A) GitHub Actions — deploy from your existing workflow using OIDC role assumption, no AWS-managed pipeline (default)
> B) AWS CodePipeline — AWS-managed pipeline triggered on GitHub push; requires one-time GitHub connection authorization in the AWS console
> C) Manual CLI — no automated pipeline; deploy via the EB/AWS CLI as documented in `MIGRATION_GUIDE.md`

**Interpret:**

- A → `design_constraints.eb_deploy_method: { "value": "github_actions", "chosen_by": "user" }`
- B → `design_constraints.eb_deploy_method: { "value": "codepipeline", "chosen_by": "user" }`
- C → `design_constraints.eb_deploy_method: { "value": "manual", "chosen_by": "user" }`

**Default:** A → `design_constraints.eb_deploy_method: { "value": "github_actions", "chosen_by": "default" }`

**Generate impact:** `"github_actions"` emits `.github/workflows/deploy-eb.yml`; `"codepipeline"` emits `terraform/pipeline.tf`; `"manual"` emits neither automation artifact.

---

### Batch 2: Data / Network

#### Q6 — Database HA Preference

> _Fires only when postgres service is present in inventory._
>
> For your PostgreSQL database(s), what high-availability configuration do you want on AWS?
>
> A) Single-AZ — lowest cost
> B) Multi-AZ — automatic failover to standby replica (RDS Multi-AZ)
> C) Multi-AZ HA — Aurora with read replicas and fast failover
> D) Match global availability posture — use same tier as Q3 answer

**Interpret:**

- A → `database_ha: "single-az"`
- B → `database_ha: "multi-az"`
- C → `database_ha: "multi-az-ha"`
- D → `database_ha: <value from Q3 availability>`

**Default:** D → matches Q3 availability answer

**Design impact:**

- `single-az` or `multi-az` → RDS PostgreSQL
- `multi-az-ha` or `multi-region` → Aurora PostgreSQL

---

#### Q6b — Migration Approach

> _Fires only when postgres service is present in inventory._
>
> How do you want to phase the migration?
>
> A) Full cutover — migrate database and application together in one maintenance window
> B) Data-first (interim cutover) — migrate database to AWS first, keep application on Render temporarily while you prepare compute migration
>
> ⚠️ Note: Option B requires interim network access from Render to your RDS instance,
> granted to a bounded allowlist of addresses (never the open internet) with TLS enforced
> first. Hybrid Render+AWS operation should be bounded to weeks, not quarters.

**Interpret:**

- A → `migration_approach: "full_cutover"`
- B → `migration_approach: "interim_cutover_data_first"` — also triggers follow-up for target exit date

**If B selected, immediately ask:**

> When do you plan to complete the full migration (move compute off Render)?
> Please provide a target date (YYYY-MM-DD format).

Validate: must be valid ISO 8601 date, must be in the future.

**On valid date:** Set `target_exit_date: "<date>"`, `interim_cutover: true`,
`ktlo_warning: "Hybrid Render+AWS operation should be bounded to weeks, not quarters."`

**Default:** A → `migration_approach: "full_cutover"`

**Design impact:** Option B triggers the interim database exposure section in MIGRATION_GUIDE.md (TLS prerequisite gate, then a scoped CIDR allowlist applied via Terraform), a Platform Risk callout, and post-migration lockdown emphasis.

---

#### Q6c — Database Migration Method

> _Fires only when postgres service is present in inventory._
>
> How would you like to migrate your PostgreSQL data to AWS?
>
> Estimated database size from your plan: ~[derive from postgres plan table max storage]
> (If you know your actual database size, tell me and I'll adjust the recommendation.)
>
> A) pg_dump / pg_restore — simplest method, requires application downtime during migration (recommended for databases under ~10GB)
> B) AWS DMS (Database Migration Service) — bulk migration with shorter downtime window for large databases (recommended for databases over ~10GB)
> ⚠️ Note: DMS can do one-time bulk migration. Continuous replication from Render Postgres depends on whether Render grants the REPLICATION role — verify before committing to this path.
> C) Bucardo — trigger-based replication for near-zero downtime (requires additional EC2 infrastructure)

**Interpret:**

- A → `migration_method: "pg_dump_restore"`
- B → `migration_method: "dms"`
- C → `migration_method: "bucardo"`

**Default:** A → `migration_method: "pg_dump_restore"`

**Size-based recommendation logic:**

- If estimated DB size < 10GB → recommend A (pg_dump_restore)
- If estimated DB size ≥ 10GB and user accepts brief downtime → recommend B (dms)
- If user requires near-zero downtime regardless of size → recommend C

**Estimating size:** Use the postgres plan table's maximum storage capacity for the detected plan tier as the estimated size. If user provides actual size, use that and record `source: "user_override"`.

**Design impact:** Determines which data migration procedure section appears in MIGRATION_GUIDE.md. DMS selection triggers the replication limitation warning.

---

#### Q7 — Redis HA

> _Fires only when key_value (Redis) service is present in inventory._
>
> Should your Redis cluster on AWS include Multi-AZ with automatic failover?
>
> A) Yes — Multi-AZ with automatic failover (higher availability, ~2x cost)
> B) No — single-node, no replication (matches Render free/starter plans)

**Interpret:**

- A → `redis_ha: true`
- B → `redis_ha: false`

**Default:** A → `redis_ha: true`

---

#### Q8 — Cron Job Target

> _Fires only when cron_job service is present in inventory._
>
> How should your Render cron jobs be run on AWS?
>
> Render cron jobs run your container on a schedule. On AWS, short-to-medium jobs
> (under 15 minutes, under 3GB memory) fit well on Lambda. Heavier jobs can use
> ECS Fargate Scheduled Tasks.
>
> A) Lambda (default) — EventBridge Scheduler + Lambda function. Simpler, lower cost, serverless. Best for jobs ≤ 15 minutes.
> B) Fargate Scheduled Tasks — ECS Fargate task triggered by EventBridge. Better for memory-intensive or long-running jobs.

**Interpret:**

- A → `cron_target: "lambda"`
- B → `cron_target: "fargate_scheduled"`

**Default:** A → `cron_target: "lambda"`

**Design impact:** Lambda default uses `cron-lambda-sizing.json` table. Cron jobs with
`fargate_fallback: true` in that table are mapped to Fargate regardless of this setting —
the sizing table can force Fargate for heavy plans even when Lambda is the user preference.

---

#### Q10 — DNS Strategy

> How do you want to manage DNS for your migrated services?
>
> A) Route 53 — migrate DNS to AWS for full integration (health checks, failover routing)
> B) External DNS — keep current DNS provider, update records manually during cutover

**Interpret:**

- A → `dns_strategy: "route53"`
- B → `dns_strategy: "external"`

**Default:** A → `dns_strategy: "route53"`

---

### Batch 3: Operational

#### Q12 — Container Registry

> Where should container images be stored for your containerized workloads?
>
> A) Amazon ECR — fully integrated with ECS/Fargate, no cross-account config needed
> B) Existing registry — you already have a container registry (Docker Hub, GitHub Container Registry, etc.)

**Interpret:**

- A → `container_registry: "ecr"`
- B → `container_registry: "external"`

**Default:** A → `container_registry: "ecr"`

---

#### Q13 — Log Retention

> How long should application logs be retained in CloudWatch Logs?
>
> A) 7 days — short retention, lowest cost
> B) 14 days — standard short-term
> C) 30 days — typical production retention
> D) 90 days — extended for debugging and compliance
> E) 365 days — long-term compliance/audit
> F) Custom — specify number of days

**Interpret:**

- A → `log_retention_days: 7`
- B → `log_retention_days: 14`
- C → `log_retention_days: 30`
- D → `log_retention_days: 90`
- E → `log_retention_days: 365`
- F → `log_retention_days: <user value>` (validate: integer 1–3653)

**Default:** C → `log_retention_days: 30`

---

#### Q14 — Alerting Preference

> How do you want to handle alerting and on-call notifications?
>
> A) CloudWatch Alarms + SNS — native AWS alerting (email, SMS, Lambda triggers)
> B) PagerDuty — integrate with existing PagerDuty setup
> C) OpsGenie — integrate with existing OpsGenie setup
> D) None for now — I'll configure alerting later

**Interpret:**

- A → `alerting: "cloudwatch"`
- B → `alerting: "pagerduty"`
- C → `alerting: "opsgenie"`
- D → `alerting: "none"`

**Default:** A → `alerting: "cloudwatch"`

---

#### Q15 — Cost Optimization Aggressiveness

> How aggressively should we optimize for cost vs. operational safety?
>
> A) Conservative — match current capacity closely, prioritize stability over savings
> B) Balanced — reasonable right-sizing with safety margins (recommended)
> C) Aggressive — minimize cost, accept tighter margins and potential scaling events

**Interpret:**

- A → `cost_optimization: "conservative"`
- B → `cost_optimization: "balanced"`
- C → `cost_optimization: "aggressive"`

**Default:** B → `cost_optimization: "balanced"`

---

## Defaults Table

| Question                  | Default               | Constraint                                                                |
| ------------------------- | --------------------- | ------------------------------------------------------------------------- |
| Q1 — Region               | B (us-west-2)         | `target_region: "us-west-2"`                                              |
| Q2 — Compliance           | A (none)              | `compliance: "none"`                                                      |
| Q3 — Availability         | B (multi-az)          | `availability: "multi-az"`                                                |
| Q4 — Maintenance          | D (flexible)          | `maintenance_window: "flexible"`                                          |
| Q5 — Env naming           | A (production)        | `environment_naming: "production"`                                        |
| Q5b — Urgency             | A (routine)           | `migration_urgency: "routine"`                                            |
| Q6 — Database HA          | D (match Q3)          | `database_ha: <Q3 value>`                                                 |
| Q6b — Migration approach  | A (full cutover)      | `migration_approach: "full_cutover"`                                      |
| Q6c — DB migration method | A (pg_dump)           | `migration_method: "pg_dump_restore"`                                     |
| Q7 — Redis HA             | A (yes)               | `redis_ha: true`                                                          |
| Q8 — Cron target          | A (lambda)            | `cron_target: "lambda"`                                                   |
| Q9 — Web compute target   | A (elastic_beanstalk) | `design_constraints.web_compute_target: "elastic_beanstalk"`              |
| Q10 — DNS                 | A (Route 53)          | `dns_strategy: "route53"`                                                 |
| Q11 — EB deploy method    | A (GitHub Actions)    | `eb_deploy_method: { "value": "github_actions", "chosen_by": "default" }` |
| Q12 — Registry            | A (ECR)               | `container_registry: "ecr"`                                               |
| Q13 — Log retention       | C (30 days)           | `log_retention_days: 30`                                                  |
| Q14 — Alerting            | A (CloudWatch)        | `alerting: "cloudwatch"`                                                  |
| Q15 — Cost optimization   | B (balanced)          | `cost_optimization: "balanced"`                                           |

When all active batches are answered (or defaults applied for the rest), control passes to
the assembler (`clarify-assemble.md`) to write and validate `preferences.json`.
