# azure-to-aws — Session Handoff

**Date:** 2026-09-06 · **Repo:** `awslabs/startups` · **Branch:** `feat/azure-to-aws`, off `feat/telemetry-hooks` at `10ca160` · **14 commits**

**Authoritative plan:** `.agents/scratchpad/azure-to-aws-implementation-plan-v2.md` (1,484 lines). **Read §13, §14 and §15 first** — they are this session's decisions, the sequencing change, and how the skill is actually tested. The Pippin artifact *Implementation Plan (rev 2)* is a **mirror** published from that file; edit the repo file and re-publish, never the mirror.

> **Read this if you read nothing else.** The goal is **Terraform-sourced Azure estates migrated end to end**. Live `az`, RDfA, billing, app-code, Bicep and ARM are all deliberately deferred (§14). Discover, Clarify and Design pass 1+2 are real and gated by three Python oracles in CI. **The gate on everything now is ONE owner decision** — Design halts on the corpus's untranslated type, and `estimate.md` requires Design completed, so nothing downstream can run until that is resolved (§8). Then **Estimate**, then Generate. `networking.md`/`messaging.md` are NOT next — see the correction in §8. Two pre-existing `drift:check` failures are NOT yours.

***

## 1. What is real, what is not

| Phase | State | Detail |
| ----- | ----- | ------ |
| **discover** | **real, verified** | Terraform only. Clustering real (seed → split → merge → tier → primary → roles). Bicep and ARM **halt** rather than half-discover |
| **clarify** | **real, verified** | 5 fragments: global, compute, database, licensing (conditional), identity. AI categories are step 6 |
| **design** | **real, verified** | Pass 1 (30 direct / 52 skip / 10 gate rows) + pass 2 for compute and database. **7 rubric files still missing** |
| estimate | skeleton | wiring only |
| generate | skeleton | wiring only |
| workshop / feedback | skeleton | sidebars; `workshop` carries `_gates: generate` |

**A run today** gets through Discover and Clarify, then Design halts. On the CORPUS the only blocker is the untranslated `azurerm_iothub` — `pending_rubric[]` is empty and 16 `services[]` are mapped. On an arbitrary REAL repo it would additionally halt on anything routed to one of the 7 missing rubric files.

Counts: `references/design-refs/` 5 of ~14 · `knowledge/design/` 1 of ~10 · `references/clustering/` 4 of 4 · `references/shared/` 7 files.

***

## 2. Commits

<table data-id="t1" data-col-sizes="90,400">
  <tr data-id="t1r0"><th data-id="t1h0">Commit</th><th data-id="t1h1">What</th></tr>
  <tr data-id="t1r1"><td data-id="t1a1"><code>940aadd</code></td><td data-id="t1b1">Step 0a — promote 8 cloud-agnostic AI refs + <code>sdk-capability-map.json</code> to <code>skills/shared/ai/</code></td></tr>
  <tr data-id="t1r2"><td data-id="t1a2"><code>c26ee33</code></td><td data-id="t1b2">Step 0b — optional <code>run_mode</code> in <code>phase-status.schema.json</code></td></tr>
  <tr data-id="t1r3"><td data-id="t1a3"><code>317c3ac</code></td><td data-id="t1b3">Step 1 — DSL backbone skeleton, §1 repo wiring, telemetry, two <code>emit.mjs</code> fixes</td></tr>
  <tr data-id="t1r4"><td data-id="t1a4"><code>01fae9b</code></td><td data-id="t1b4">Terraform discovery made real + the fixture/oracle</td></tr>
  <tr data-id="t1r5"><td data-id="t1a5"><code>a9682c9</code></td><td data-id="t1b5">Ran the oracle; fixed 5 defects; promoted it to a golden CI gate</td></tr>
  <tr data-id="t1r6"><td data-id="t1a6"><code>a78594c</code></td><td data-id="t1b6">Committed the plan doc (untracked across two sessions)</td></tr>
  <tr data-id="t1r7"><td data-id="t1a7"><code>bd398c7</code></td><td data-id="t1b7"><strong>Step 3</strong> — the mapping algorithm's pass 1, and an oracle for it</td></tr>
  <tr data-id="t1r8"><td data-id="t1a8"><code>2617c98</code></td><td data-id="t1b8">Closed the 6 contract gaps capability run 1 found</td></tr>
  <tr data-id="t1r9"><td data-id="t1a9"><code>e3a33be</code></td><td data-id="t1b9">Gave <code>aws-design.json</code> a schema; stopped <code>index.md</code> printing the answers</td></tr>
  <tr data-id="t1r10"><td data-id="t1a10"><code>d45fd28</code></td><td data-id="t1b10">Named the repo copy of the plan authoritative (it had forked from Pippin)</td></tr>
  <tr data-id="t1r11"><td data-id="t1a11"><code>6ed8a82</code></td><td data-id="t1b11">Handoff for 2026-09-05</td></tr>
  <tr data-id="t1r12"><td data-id="t1a12"><code>c8dc0b2</code></td><td data-id="t1b12"><strong>Step 5</strong> — compute + database rubrics, real clustering, solid inventory</td></tr>
  <tr data-id="t1r13"><td data-id="t1a13"><code>cdfe8b8</code></td><td data-id="t1b13">Closed the 2 regressions capability run 3 found</td></tr>
  <tr data-id="t1r14"><td data-id="t1a14"><code>bdd20ae</code></td><td data-id="t1b14"><strong>Step 5a</strong> — Clarify's four infra categories, and gate clustering</td></tr>
</table>

***

## 3. Locked decisions — do not re-litigate

**From the plan's §0/§4/§7a, owner-confirmed:** DSL-native, not a gcp-style prose state machine · gcp's product surface · canonical `Microsoft.*` ARM types as the mapping key · one `discover-iac.md` for all three dialects with an `{ _always: true }` trigger · resource-group-seeded clustering refined by typed edges · a pattern never overrides a `deterministic` mapping · **App Runner banned everywhere including trigger text** · App Service → Elastic Beanstalk default, Fargate override, EKS for existing K8s teams · telemetry wired now · **`x86_64` is the default architecture, NOT Graviton** (Windows/.NET — this will look like a bug).

**Owner decisions 11.3–11.6:** Azure SQL defaults to RDS SQL Server, `Deferred` only for Managed Instance and elastic pools · Event Hubs is protocol-only (`kafka_enabled` → MSK) · Azure Files is protocol-driven (SMB → FSx, NFS → EFS) · App Insights / Log Analytics are Skip Mappings with a CloudWatch note.

**This session added 21 more — §13 of the plan, with a reason per row.** The ones most likely to be second-guessed:

| Decision | Why |
| -------- | --- |
| **11.5 disturbs NO Direct Mappings row.** `storageAccounts` keeps `Always → S3` | canonicalization already makes a file share its own `resources[]` entry, so it is never inside the account's mapping unit |
| **An UNTRANSLATED type is cost-bearing by default and STOPs** | it has no SKU, no consumption row, no provider namespace — the skill cannot show a resource it could not NAME is free |
| **Direct Mappings is 30 rows, not §7a.3's 10** | 4 were necessity (subnets + storage children reach the unknown-type policy without a row); the rest from the coverage pass |
| **`.terraform/modules/` is READ** | it holds module SOURCE only. The blanket ban was for state and was over-broad; under it an Azure-Verified-Modules repo returns a nearly empty inventory |
| **`network` and `secret_ref` are AMBIENT edges and never merge** | everything shares subnets, one Key Vault serves the estate — merging collapses the estate into one cluster |
| **Fragments compute rows; the ASSEMBLER owns the Clarify conversation** | five fragments each presenting would give five sheets. gcp runs one, and the postcondition says "sheet", singular |
| **`ESSENTIAL` + `value: null` IS the completion gate** | the only way the contract can say "shown and not answered". A run that completes anyway invented consent |
| **A default-valued row stays `PROPOSED`, never `DETECTED`** | Design prints "you chose X" differently from "we assumed X" — only possible if Clarify recorded which |
| **`availability` is ESSENTIAL when the source is zone-redundant** | downgrading resilience silently is one mistake; reading their HA config as the answer is the other — it says what they BOUGHT |
| **`identity` defaults to a fresh IAM Identity Center, not Entra federation** | federation leaves the migration depending on the cloud being left |

***

## 4. Correction to the 2026-09-05 handoff

It said **`bedrock-quotas.md` has zero inbound references** and asked whether it was dead. **Wrong — do not delete it.** Two real load references: `gcp-to-aws/references/phases/design/design-ai.md:192` and `estimate/estimate-ai.md:108`. The claim came from a grep that excluded `vendored/ai/bedrock-quotas.md` to skip the vendored copy, which also ate every *reference* to that path.

***

## 5. How this is tested — the most transferable part

### `_assert` proves nothing

The model both PRODUCES the artifact and EVALUATES the assertion against it. There is no independent oracle. **Never judge this skill by whether a run completes.** Related: `parse.ts:49` returns null for a file not starting with `---`, so a prose skill passes `lint:frontmatter` green while entirely unvalidated — which is what `gcp-to-aws` does (`0 phase file(s) checked`). **Always read the count.** azure reports **7**.

### Two kinds of check — build both

| | Catches | Scales with |
| - | ------- | ----------- |
| **Extensional** — run on an input, compare to a golden | wrong ANSWERS | corpus breadth |
| **Intensional** — read the artifacts, assert a relationship between them, no input | wrong CONTRACTS | pairs of files |

Only extensional existed until this session. **Every defect the capability runs found was intensional** — two files disagreeing — and extensional tests are structurally blind to those. The 53-orphan regression existed independently of any input; no fixture could have caught it by running.

**Practice: for every pair of files where one obliges the other, write the pairing check.** Unguarded pairs today: edge vocabulary → merge/ambient rule · Design warning codes → codes used (Discover's IS guarded) · primary ranks → the split guard · `index.md` Reference column → file exists.

### The capability test — make it a required gate per content step

Copy the corpus OUTSIDE the repo. Dispatch a FRESH isolated agent at `SKILL.md`. **Hard-prohibit** `fixtures/`, `expected-*`, `check_expected*`, and anything under a directory starting `after-`. Require an exhaustive notes file. Then run the oracles and diff against the golden.

**Three runs, three different classes of defect, and 44 passing mutations found none of them.** Mutations test the ORACLE; a fresh context tests the TEACHING.

<table data-id="t2" data-col-sizes="60,400">
  <tr data-id="t2r0"><th data-id="t2h0">Run</th><th data-id="t2h1">Found</th></tr>
  <tr data-id="t2r1"><td data-id="t2a1">1</td><td data-id="t2b1">Passed the Discover oracle, then diverged on <strong>six things no ref stated</strong> — undefined <code>warnings[]</code>, the <code>subscription_id_source</code> contradiction, <code>data_ref</code> missing from the canonical edge list, the unstated <code>/fileServices/default/</code> segment, four missing per-type attribute rows, a live postcondition-vs-assembler contradiction</td></tr>
  <tr data-id="t2r2"><td data-id="t2a2">2</td><td data-id="t2b2">Failed Design in <strong>7 places, all under-specification</strong>. <strong>And proved the halt guard holds under pressure</strong>: told to map six resources whose rubric file was absent, it mapped NONE — and reported being <em>strongly tempted</em>, because <code>index.md</code> printed the answers next to the HALT</td></tr>
  <tr data-id="t2r3"><td data-id="t2a3">3</td><td data-id="t2b3">Confirmed the 3 inventory fixes end to end, then found the <strong>53-orphan regression</strong> and the <strong>16-vs-3 cluster over-fragmentation</strong></td></tr>
</table>

**Clarify cannot be reached this way** — `_interactive: true`, so a dispatched agent has no user. `clarify-answers.json` is a scripted answer set that substitutes for one. It tests BRANCHING (which rows fire, which are ESSENTIAL, which are N/A) and **nothing about wording, batching or tone** — those need a human.

### Goldens are deliberately FAILING states

`after-design-halted/` halts on the untranslated type. `after-clarify/` is BLOCKED because the scripted user declines to state spend. **The gate matters more than the happy path.**

And **a hand-authored golden drifts from a prose-only ref by construction.** That bit twice in one session, in opposite directions. **If the oracle asserts it, a skill file must require it.**

***

## 6. The fixture

`fixtures/azure-iac-terraform/` in both trees. **Selection rule: only facts where a plausible improvisation and the correct answer DIVERGE.** Facts a model gets right by accident are deliberately NOT asserted. **Preserve this rule when extending.**

<table data-id="t3" data-col-sizes="300,400">
  <tr data-id="t3r0"><th data-id="t3h0">Path</th><th data-id="t3h1">Role</th></tr>
  <tr data-id="t3r1"><td data-id="t3a1"><code>workspace-terraform/</code></td><td data-id="t3b1">the committed INPUT — 31 resources, a resolvable module (source under <code>.terraform/modules/</code>), an unresolvable module, an association-only resource</td></tr>
  <tr data-id="t3r2"><td data-id="t3a2"><code>after-discover/</code></td><td data-id="t3b2">GOLDEN — 29-resource inventory + 4-cluster artifact</td></tr>
  <tr data-id="t3r3"><td data-id="t3a3"><code>after-clarify/</code></td><td data-id="t3b3">GOLDEN — a <strong>BLOCKED</strong> clarify</td></tr>
  <tr data-id="t3r4"><td data-id="t3a4"><code>after-design-halted/</code></td><td data-id="t3b4">GOLDEN — a <strong>HALTED</strong> design, 16 services</td></tr>
  <tr data-id="t3r5"><td data-id="t3a5"><code>clarify-answers.json</code></td><td data-id="t3b5">the scripted user</td></tr>
</table>

**The wrong answers the oracle names**, because each is what a capable improviser reaches for:

| Corpus construct | Tempting | Correct |
| ---------------- | -------- | ------- |
| Cosmos `kind: MongoDB` | DynamoDB | **DocumentDB** |
| share `enabled_protocol = "SMB"` | EFS | **FSx for Windows File Server** |
| Event Hubs `kafka_enabled = true` | Kinesis | **MSK** |
| S1 plan hosting 5 web apps | Fargate | **Elastic Beanstalk** |
| Y1 consumption plan + function app | Elastic Beanstalk | **Lambda** |
| Windows VM | Fargate | **EC2** |
| Postgres with `ZoneRedundant` source HA | Aurora | **RDS single-AZ** + a downgrade finding |
| `azurerm_bastion_host` | an EC2 bastion | **Session Manager** — no host, free |
| the 1-app and 0-app plans | asked the isolation question | **N/A** |
| Cosmos Mongo account | asked the RU/s split | **N/A** — only the Core API converts |

**Mutation coverage: 71 injected across the session, 71 caught**, each naming the rule violated.

**`azurerm_iothub` is the untranslated-type case, chosen for DURABLE absence.** An earlier draft used `azurerm_dev_test_lab`; the first coverage pass added it to the canonicalization table and the fixture silently stopped testing anything. Any fixture depending on a type being ABSENT has that failure mode.

***

## 7. Gate status

`mise`, `dprint`, `markdownlint-cli2`, `gitleaks`, `terraform` are **not installed**. Run directly:

```
node <plugin>/tools/frontmatter-validator/validate.ts <plugin>/skills/<skill>
node advisor/plugins/aws-startup-advisor/tools/cross-plugin-drift.ts
node <plugin>/tools/sync-vendored-shared.ts --check
python3 <plugin>/tools/model-id-lint.py
node <plugin>/tools/fixtures-check.ts . <plugin>
python3 <plugin>/tools/run-asserters.py
```

<table data-id="t4" data-col-sizes="250,400">
  <tr data-id="t4r0"><th data-id="t4h0">Gate</th><th data-id="t4h1">State</th></tr>
  <tr data-id="t4r1"><td data-id="t4a1"><code>lint:frontmatter</code></td><td data-id="t4b1"><strong>green</strong>, 7 phase files, both trees — verified NON-VACUOUS (a broken <code>_knowledge</code> path fails it)</td></tr>
  <tr data-id="t4r2"><td data-id="t4a2"><code>shared:check</code></td><td data-id="t4b2">green, 4 vendoring skills</td></tr>
  <tr data-id="t4r3"><td data-id="t4a3"><code>drift:check</code></td><td data-id="t4b3"><strong>RED on 2 pre-existing files — NOT from this branch</strong></td></tr>
  <tr data-id="t4r4"><td data-id="t4a4"><code>fixtures:check</code></td><td data-id="t4b4">green (101 json, 11 asserters)</td></tr>
  <tr data-id="t4r5"><td data-id="t4a5"><code>fixtures:assert</code></td><td data-id="t4b5">green both trees — <strong>7 golden, 4 smoke</strong></td></tr>
  <tr data-id="t4r6"><td data-id="t4a6"><code>lint:model-ids</code></td><td data-id="t4b6">green</td></tr>
  <tr data-id="t4r7"><td data-id="t4a7"><code>lint:md</code> / <code>fmt:check</code></td><td data-id="t4b7"><strong>UNVERIFIED</strong> — dprint + markdownlint absent, npx cannot fetch offline</td></tr>
  <tr data-id="t4r8"><td data-id="t4a8"><code>heroku-eb-runtime-settings.test.ts</code></td><td data-id="t4b8">7 pass / 5 fail, <strong>pre-existing</strong>, needs <code>terraform</code></td></tr>
</table>

### The `drift:check` blocker — four sessions old, needs an owner

Fails on `skills/gcp-to-aws/SKILL.md` and `skills/heroku-to-aws/SKILL.md`. **Predates this branch.** Telemetry landed advisor-only: `migrate/plugins/migration-to-aws` has **no `hooks/` directory**, so the advisor copies carry a frontmatter `hooks:` block and a consent section the migrate copies cannot (the hook command would resolve to a nonexistent file, and the emitter-path search pattern names the advisor plugin, which is not a normalized token class). Deliberately **not** allowlisted — it is someone else's drift. The fix is two `ALLOWLIST` entries; the reasoning is already a comment above the `azure-to-aws` entry.

**Before any PR:** `mise run fmt` (dprint re-pads markdown tables; ours are hand-aligned) and `gitleaks`.

***

## 8. Where to go next

**Goal: Terraform-sourced Azure estates migrated end to end.** Source breadth waits (plan §14).

> **CORRECTION, made while preparing this handoff.** An earlier draft said `networking.md` +
> `messaging.md` were next. **They are not on the critical path.** The corpus routes **zero**
> resources to a missing rubric file — Design already emits 16 `services[]` with
> `pending_rubric[]` **empty**, and halts on exactly ONE thing: the untranslated
> `azurerm_iothub`. Check `after-design-halted/aws-design.json`'s `halt.blocking` and
> `pending_rubric` before trusting either ordering.
>
> Consequence: those two rubrics are needed before any **real customer repo** (7 and 5 types),
> but they block nothing on the fixture. Estimate and Generate are on the critical path for
> BOTH definitions of the goal; `networking.md` for only one.

### The blocking decision, and it is now blocking

`estimate.md` carries `_check_phase_completed: design`, and Design **GATE_FAILs** on the corpus
because of the untranslated type. So **Estimate can never run on the corpus, and neither can
Generate, until that halt is resolved.** What was an open product question in §13.7 is now the
gate on the whole end-to-end goal. Two paths:

| Path | What it costs |
| ---- | ------------- |
| **A — the user override** (§13.7 #1). Continue past an untranslated type when the user explicitly accepts it; record the under-report in the artifact, name the skipped resources in the report, and degrade the estimate's confidence label. | A real behaviour change, and it softens a currently absolute rule. But it is the behaviour a real customer needs, and it makes the corpus runnable end to end without touching the corpus. |
| **B — a variant inventory.** Commit a second golden identical to `after-discover/` but with `iac_metadata.untranslated_types` cleared, modelling the state AFTER the user files the type. Build Estimate and Generate against that. | One extra committed file and no behaviour change. Keeps the STOP absolute. Does not help a real repo. |

**A is the recommendation** — it is the behaviour the product needs, and the STOP stays the
default with the override an explicit, recorded decision. But it is the owner's call.

### Order, once that is settled

<table data-id="t5" data-col-sizes="90,400">
  <tr data-id="t5r0"><th data-id="t5h0">Step</th><th data-id="t5h1">What</th></tr>
  <tr data-id="t5r1"><td data-id="t5a1">5a</td><td data-id="t5b1"><strong>done</strong> — Clarify's four infra categories</td></tr>
  <tr data-id="t5r2"><td data-id="t5a2"><strong>5c</strong></td><td data-id="t5b2"><strong>NEXT — Estimate.</strong> Dual output (1:1 lift vs right-sized), the post-Estimate decision gate that writes <code>run_mode</code>, the licensing delta line, and the ~9 <code>knowledge/design/*.json</code> sizing tables. <strong>Its fixtures need TOLERANCES</strong>, not exact assertions — pricing drifts, so exact totals would be permanently brittle. First phase where that is true</td></tr>
  <tr data-id="t5r3"><td data-id="t5a3">5e</td><td data-id="t5b3">Generate — Terraform output, migration guide, report, scripts. Completes the corpus end to end</td></tr>
  <tr data-id="t5r4"><td data-id="t5a4">5d</td><td data-id="t5b4"><code>patterns.md</code> — not a gate, but the report leads with cluster-level rationale and there is none without it, so the customer-facing headline is empty</td></tr>
  <tr data-id="t5r5"><td data-id="t5a5">5f</td><td data-id="t5b5"><code>workshop</code> + <code>feedback</code> sidebars (<code>workshop</code> carries <code>_gates: generate</code>)</td></tr>
  <tr data-id="t5r6"><td data-id="t5a6"><strong>5b</strong></td><td data-id="t5b6"><code>networking.md</code> (7 types) + <code>messaging.md</code> (5) + thin <code>storage.md</code> / <code>identity.md</code> (1 each). <strong>Needed before any real repo, blocks nothing on the corpus.</strong> Independent of 5c–5f so it parallelises — and it needs corpus EXTENSION to be testable at all, since nothing in the fixture reaches these rubrics</td></tr>
  <tr data-id="t5r7"><td data-id="t5a7">6</td><td data-id="t5b7">THEN source breadth: Bicep + ARM (cheap — they hand you the ARM type), then billing, app-code, RDfA, live <code>az</code> (security contract FIRST)</td></tr>
</table>

`analytics.md` (2 types) and `gpu-hpc.md` (1) sit with 5b. `licensing.md` and `patterns.md` are
routed from ZERO types — reached conditionally, not by type.

### Three decisions waiting on the owner

1. **The untranslated-type STOP is unconditional and WILL fire on real repos.** 137 types is not the provider surface, so one unknown type halts Design and the only path forward is "we add a row, you re-run." Proposal: an **explicit user override** — continue, record the under-report, name the skipped resources in the report, and **degrade the estimate's confidence label**. STOP stays the default. Softens a currently absolute rule, so it needs a decision.
2. **An exported ARM template is not "declared intent"** and the precedence table assumes it is. `az deployment group export` produces a SNAPSHOT, so it should rank near live, not below RDfA, and carries no module structure for Generate to imitate. Decide before writing `extract-arm.md`.
3. **The `drift:check` blocker** (§7).

***

## 9. Traps that will bite a fresh session

- **Every skill edit is a TWO-TREE edit** (`advisor/` + `migrate/`) or `drift:check` fails.
- **`lint:frontmatter` passing means nothing if the count is 0.** Read the count.
- **`_assert` has no teeth.** `generate.md`'s `run_mode` consent check is an `_assert` and says so in its own prose.
- **A hand-authored golden drifts from a prose-only ref by construction.** If the oracle asserts it, a skill file must require it.
- **Keep `index.md`'s candidate sets unordered and default-free.** The moment a default appears there, the halt guard is bypassable — capability run 2 reported being strongly tempted by exactly that.
- **Adding a canonicalization row obliges a disposition row.** 53 orphans once; now asserted at zero.
- **Do not build a fixture that depends on a type being ABSENT.** A coverage pass silently disarms it.
- **A missing SIZING table is treated more softly than a missing RUBRIC file**, deliberately: the first degrades a number's precision, the second fabricates the answer. Only the second halts.
- **zsh, not bash.** Unquoted `$var` does not word-split; `$VAR:h` is a history modifier.
- **`emit.mjs` needs a hook payload on stdin** or it throws (fail-open, so zero telemetry with no signal).
- **gitleaks runs over this repo.** The sentinel is `FIXTURE_SENTINEL_MUST_NOT_APPEAR`.
- **`x86_64` default, not Graviton.** Deliberate; Windows/.NET prevalence. It will look like a bug.
- **App Runner is banned**, including in trigger text and candidate lists.
- **Unfixed, known:** most `azure_id` values carry a `tf:<local>` name segment because the corpus names everything `${var.prefix}`, so they are not real ARM IDs and cannot be drift-matched against a live capture. Flagged by `name_expression_unresolved` (one entry per run). The fix — a per-resource `azure_id_synthetic` marker — belongs with the live `az` path, where the comparison it protects actually happens.
