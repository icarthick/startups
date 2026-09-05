# azure-to-aws — Session Handoff

**Date:** 2026-09-05 · **Repo:** `awslabs/startups` · **Branch:** `feat/azure-to-aws`, off `feat/telemetry-hooks` at `10ca160`

**Authoritative plan:** `.agents/scratchpad/azure-to-aws-implementation-plan-v2.md` — **committed** as of this session (`a78594c`). The Pippin artifact *Implementation Plan (rev 2)* is a **mirror**, published from that file at v4. They had forked by 8k characters; edit the repo file and re-publish, never the mirror.

> **Read this if you read nothing else.** Build steps 0, 1, and **3** are done. Discover (Terraform) and Design (pass 1) are both real and both gated by external Python oracles in CI. Two capability tests were run from clean contexts, and the second one proved the **halt guard holds under pressure** — which is the load-bearing claim of this whole design. The next task is step 5 (`compute.md` + `database.md`) or step 4 (clustering + patterns); they parallelize. Two pre-existing `drift:check` failures are still NOT yours and still outstanding.

***

## 1. Correction to the previous handoff — read before acting on it

The 2026-09-04 handoff said **`bedrock-quotas.md` had zero inbound references** and asked whether it was dead. **That is wrong. Do not delete it.** It has two real load references:

- `gcp-to-aws/references/phases/design/design-ai.md:192` — "Quota risk assessment (per `references/vendored/ai/bedrock-quotas.md`)"
- `gcp-to-aws/references/phases/estimate/estimate-ai.md:108` — the `quota_risk = "high"` branch

The claim came from a grep that excluded `vendored/ai/bedrock-quotas.md` to skip the vendored copy, which also ate every *reference* to that path. Nothing was lost and no load condition is missing.

***

## 2. Commits on this branch

<table data-id="c0" data-col-sizes="80,400">
  <tr data-id="c0r0"><th data-id="c0h0">Commit</th><th data-id="c0h1">What</th></tr>
  <tr data-id="c0r1"><td data-id="c0a1"><code>940aadd</code></td><td data-id="c0b1"><strong>Step 0a</strong> — promote 8 cloud-agnostic AI refs + <code>sdk-capability-map.json</code> to <code>skills/shared/ai/</code></td></tr>
  <tr data-id="c0r2"><td data-id="c0a2"><code>c26ee33</code></td><td data-id="c0b2"><strong>Step 0b</strong> — optional <code>run_mode</code> enum in <code>phase-status.schema.json</code></td></tr>
  <tr data-id="c0r3"><td data-id="c0a3"><code>317c3ac</code></td><td data-id="c0b3"><strong>Step 1</strong> — DSL backbone skeleton, §1 repo wiring, telemetry, two <code>emit.mjs</code> fixes</td></tr>
  <tr data-id="c0r4"><td data-id="c0a4"><code>01fae9b</code></td><td data-id="c0b4">Terraform discovery made real + the fixture/oracle</td></tr>
  <tr data-id="c0r5"><td data-id="c0a5"><code>a9682c9</code></td><td data-id="c0b5">Ran the oracle; fixed the 5 defects it found; promoted it to a golden CI gate</td></tr>
  <tr data-id="c0r6"><td data-id="c0a6"><code>a78594c</code></td><td data-id="c0b6">Committed the plan doc (was untracked across two sessions)</td></tr>
  <tr data-id="c0r7"><td data-id="c0a7"><code>bd398c7</code></td><td data-id="c0b7"><strong>Step 3</strong> — the mapping algorithm's pass 1, and an oracle for it</td></tr>
  <tr data-id="c0r8"><td data-id="c0a8"><code>2617c98</code></td><td data-id="c0b8">Closed the six contract gaps the first capability test found</td></tr>
  <tr data-id="c0r9"><td data-id="c0a9"><code>e3a33be</code></td><td data-id="c0b9">Gave <code>aws-design.json</code> a schema; stopped <code>index.md</code> printing the answers</td></tr>
  <tr data-id="c0r10"><td data-id="c0a10"><code>d45fd28</code></td><td data-id="c0b10">Named the repo copy of the plan authoritative</td></tr>
</table>

***

## 3. The capability test is the most valuable tool this project has

**Method.** Copy `fixtures/azure-iac-terraform/workspace-terraform/` to a scratch dir outside the repo. Dispatch a FRESH isolated agent at it, pointed only at the skill's `SKILL.md`. **Hard-prohibit** reading anything under `fixtures/`, any `expected-*` / `check_expected*` file, and any `after-*` directory — those are the answer keys. Require an exhaustive notes file recording every point the skill left it guessing. Then run the Python oracles against its output and diff against the golden tree.

**It has now paid for itself twice, and differently each time.** This is the argument for making it a required gate per content step rather than an occasional exercise:

<table data-id="c1" data-col-sizes="60,400">
  <tr data-id="c1r0"><th data-id="c1h0">Run</th><th data-id="c1h1">What it found that nothing else could</th></tr>
  <tr data-id="c1r1"><td data-id="c1a1">1</td><td data-id="c1b1">PASSED the Discover oracle — every casing trap, the fan-in edges, the cross-RG <code>data_ref</code>, child resource-group inheritance, the secret boundary, all correct from the refs alone. Then diverged from the golden on <strong>six things no ref stated</strong>: undefined <code>warnings[]</code>, a <code>subscription_id_source</code> contradiction, <code>data_ref</code> missing from the canonical edge list, the unstated <code>/fileServices/default/</code> segment, four missing per-type attribute rows, and a live postcondition-vs-assembler contradiction. <strong>No existing assertion caught any of them.</strong></td></tr>
  <tr data-id="c1r2"><td data-id="c1a2">2</td><td data-id="c1b2">Passed Discover including all the new contract checks (so the fixes held), then failed Design in 7 places — <strong>all of them under-specification, none improvisation</strong>. Found the missing <code>aws-design.json</code> schema, an unsatisfiable cluster postcondition, and a self-contradicting <code>index.md</code>.</td></tr>
</table>

**Crucially: 44 passing mutation tests found none of these.** Mutations test the *oracle*; a fresh context tests the *teaching*. They are not substitutes.

### The halt guard holds — the single most important result

Run 2 was told to map six resources whose rubric file does not exist. It produced **no mapping for any of them**, recording each in `pending_rubric[]` with its missing `ref_file`. Unprompted, it reported being *strongly* tempted not to: `index.md`'s "Typical AWS target" column printed the answers and `fast-path.md`'s Preferred-Target table printed the tie-breaker, so a complete and plausible compute + database design was available without opening `compute.md` — and every shape assertion would have passed it.

That is the false-green thesis validated live. It also means the hazard was real, so `index.md`'s right-hand column is no longer an answer key: rubric rows now carry an **unordered candidate set in braces**, no defaults, no preference ordering, and the column note says plainly that being able to answer from the column alone means the row is wrong. **Preserve that property when you add rubric files.**

***

## 4. The false-green problem (unchanged, still the organising principle)

`_assert` verifies **shape, never correctness**, and the model both produces the artifact and evaluates the assertion against it. There is no independent oracle. Strip all extraction rules from `discover-iac.md` and a run still emits `HANDOFF_OK` with output stamped `confidence: deterministic` that came from a prior, not a table — and two runs disagree.

**Corollary: never judge this skill by whether a run completes. Judge it by a Python asserter, and by what a fresh context gets wrong.**

Related trap: `parse.ts:49` returns null for a file not starting with `---`, so a prose-shaped skill passes `lint:frontmatter` green while entirely unvalidated. **Always read the count.** azure-to-aws reports **7**.

***

## 5. What is built

### Discover — Terraform only, verified

| File | Role |
| --- | --- |
| `references/shared/arm-type-canonicalization.md` | `azurerm_* → Microsoft.*`, 6 traps, `azure_id` reconstruction incl. the `/default/` singleton segment |
| `references/shared/extract-terraform.md` | extraction, per-type attributes, edges, the secret boundary |
| `references/shared/schema-discover-azure.md` | inventory + clusters contract, canonical edge vocabulary, **closed 7-code `warnings[]` vocabulary** |
| `references/phases/discover/discover-iac.md` | dialect detection, canonicalization, **halt guard** |

The six traps: `Microsoft.Web/functionApps` **does not exist**; the plan is `serverfarms` all-lowercase while `serverFarmId` is the camelCase *property*; `Microsoft.Cache/Redis` has a **capital R**; Cosmos's provider is still `DocumentDB`; Azure OpenAI is a Cognitive Services account with `kind: OpenAI`; a resource group's own ID has **no `/providers/` segment**.

Two contract fixes worth knowing: **containment is deliberately not an edge** (an ARM `azure_id` contains its parent's as a literal prefix, so it is derivable by truncation), and **observability links live in `config`, not `edges[]`** (an edge implies a dependency the architecture preserves; that one does not survive the migration). Clusters carry **`justification`** (`seed:resource_group` today) so an unrefined cluster's empty `edges[]` is legitimate rather than a silent gap.

### Design — pass 1 only, verified

| File | Role |
| --- | --- |
| `knowledge/design/fast-path-services.json` | the disposition table: 17 direct rows, 18 skip rows, 5 gate rows, hard blockers |
| `references/design-refs/fast-path.md` | the admission test, the 4-tier confidence vocabulary, the apply order, Preferred Targets |
| `references/design-refs/index.md` | canonical type → rubric routing, with the HALT guard and candidate sets |
| `references/design-refs/specialist-gates.md` | what a gate is, its precedence, what it emits, the 5 gates and why each |
| `references/shared/schema-design-aws.md` | **the `aws-design.json` contract** — added because its absence caused 5 oracle failures |

**Three deltas from the plan, all deliberate:**

1. **The plan's 10-row Direct Mappings table is 17.** Four rows are additions of necessity: canonicalization emits subnets and the three storage-service children as their own child-typed resources, so without a row each reaches the unknown-type policy, matches "sits in a network/data provider namespace", and **STOPs the design on every real estate**. §7a.3 fixed the row set before the child-type vocabulary existed.
2. **Three rows are protocol/API-conditioned and still `deterministic`** — SMB/NFS share, `kafka_enabled`, the Cosmos API. Owner decisions 11.4 and 11.5 say protocol is the *whole* rubric, which means there is no rubric left, only a lookup. Same shape as gcp's `google_sql_database_instance` (SQL Server) row.
3. **Decision 11.5 disturbs no row.** Canonicalization already makes a file share its own `resources[]` entry, so it is never inside the account's mapping unit. The account keeps `Always → S3` for its blob surface; its only condition is `account_kind == FileStorage`, where there is no blob surface at all.

**An untranslated type is cost-bearing BY DEFAULT and STOPs.** §7a.4's three-part test cannot clear it — no SKU, no consumption row, no provider namespace — and the skill cannot demonstrate that a resource it could not *name* is free. So Design reads `iac_metadata.untranslated_types` as a **separate input**, because Discover drops those resources from `resources[]` entirely and iterating `resources[]` cannot find them.

**A STOP writes the artifact.** Everything determined stays in, plus a `halt` object, and the gate fails on its own merits. Discarding the work would make the user re-run the phase to learn one missing table row, hide which resources were already fine, and make the halt untestable.

***

## 6. The oracles

`fixtures/azure-iac-terraform/` in both trees. **Selection rule: only facts where a plausible improvisation and the correct answer DIVERGE.** Facts a model gets right by accident are deliberately not asserted — they cost review attention and prove nothing. **Preserve this rule when extending.**

<table data-id="c2" data-col-sizes="300,400">
  <tr data-id="c2r0"><th data-id="c2h0">Path</th><th data-id="c2h1">Role</th></tr>
  <tr data-id="c2r1"><td data-id="c2a1"><code>workspace-terraform/</code></td><td data-id="c2b1">the committed INPUT — 28 resources + 1 unresolvable module</td></tr>
  <tr data-id="c2r2"><td data-id="c2a2"><code>after-discover/</code></td><td data-id="c2b2">GOLDEN Discover output — 27 resources</td></tr>
  <tr data-id="c2r3"><td data-id="c2a3"><code>after-design-halted/</code></td><td data-id="c2b3">GOLDEN Design output — a <strong>halted</strong> design, deliberately</td></tr>
</table>

Both registered **golden** in `tools/run-asserters.py`. `fixtures:assert` reports **6 golden / 4 smoke**.

**The Design oracle validates the TABLE, not just the design.** Required rows, the precedence invariant (a canonical type resolves to at most one disposition), and the App Runner ban. And the `deterministic` label is checked in **both** directions: every expected row carries it, and every entry carrying it names a type that really is in `direct_mappings` with a target that row allows. **The second direction is what catches an improvised label.**

Three rows have a famous wrong answer, and the oracle names it on failure:

| Corpus construct | The improviser's answer | The table's answer |
| --- | --- | --- |
| Cosmos account, `kind: MongoDB` | DynamoDB | **DocumentDB** |
| storage share, `enabled_protocol = "SMB"` | EFS | **FSx for Windows File Server** |
| Event Hubs namespace, `kafka_enabled = true` | Kinesis | **MSK** |

**Mutation coverage: 44 injected, 44 caught, each naming the rule violated.** Including the 5× App Service Plan fan-out, a plan sized from app count, an untranslated type recorded as a benign skip, clusters given a plausible `recognized` architecture, and a halt naming `compute.md` but not `database.md`.

***

## 7. Phase status — only Discover can reach `HANDOFF_OK`

All seven phases are wired and frontmatter-valid. Content:

<table data-id="c3" data-col-sizes="110,110,400">
  <tr data-id="c3r0"><th data-id="c3h0">Phase</th><th data-id="c3h1">State</th><th data-id="c3h2">Detail</th></tr>
  <tr data-id="c3r1"><td data-id="c3a1"><strong>discover</strong></td><td data-id="c3b1">partial, <strong>verified</strong></td><td data-id="c3c1">Terraform only (1 of 5 sources). Bicep and ARM <strong>halt</strong> rather than half-discover. Clustering is the RG seed only</td></tr>
  <tr data-id="c3r2"><td data-id="c3a2">clarify</td><td data-id="c3b2">skeleton</td><td data-id="c3c2">Runs, then <strong>fails its own postconditions</strong> — identity, licensing, pattern confirmation, and the isolation question all assert the finished contract and only <code>clarify-global.md</code> exists</td></tr>
  <tr data-id="c3r3"><td data-id="c3a3"><strong>design</strong></td><td data-id="c3b3">partial, <strong>verified</strong></td><td data-id="c3c3">Pass 1 only. Pass 2 rubrics absent, so it <strong>always halts</strong></td></tr>
  <tr data-id="c3r4"><td data-id="c3a4">estimate / workshop / generate / feedback</td><td data-id="c3b4">skeleton</td><td data-id="c3c4">Wiring plus a <code>## Status</code> block naming the build step that fills each</td></tr>
</table>

`design-refs/` has 3 of ~14 files; `knowledge/` has 1 of ~10 tables; `references/clustering/` does not exist. Postconditions encode the **finished** contract on purpose, so a category landing later cannot land silently — its assert fails until the unit exists.

### The Clarify testing gap — decide before step 5

**Clarify is the one phase the capability-test method cannot reach.** It is `_interactive: true`, so a dispatched isolated agent has no user to answer the assumption sheet. Both runs skipped it only because they were told to, and run 2 had to fake a `preferences.json` and mark `clarify: completed` — which it correctly called out as a lie the state schema forces (there is no `skipped` status).

When step 5 lands the Clarify categories, the oracle pattern will not reach them. That needs a scripted answer set fed as a fixture, so the sheet's **branching** is testable even though the interaction is not. **Decide this before step 5, not after.**

***

## 8. Gate status — how to verify, and what is already red

`mise`, `dprint`, `markdownlint-cli2`, `gitleaks`, and `terraform` are **not installed** on this box. Run the tools directly:

```
node <plugin>/tools/frontmatter-validator/validate.ts <plugin>/skills/<skill>
node advisor/plugins/aws-startup-advisor/tools/cross-plugin-drift.ts
node <plugin>/tools/sync-vendored-shared.ts --check
python3 <plugin>/tools/model-id-lint.py
node <plugin>/tools/fixtures-check.ts . <plugin>
python3 <plugin>/tools/run-asserters.py
```

<table data-id="c4" data-col-sizes="240,400">
  <tr data-id="c4r0"><th data-id="c4h0">Gate</th><th data-id="c4h1">State</th></tr>
  <tr data-id="c4r1"><td data-id="c4a1"><code>lint:frontmatter</code></td><td data-id="c4b1"><strong>green</strong>, 7 phase files, both trees — and verified NON-VACUOUS (a broken <code>_knowledge</code> path fails it)</td></tr>
  <tr data-id="c4r2"><td data-id="c4a2"><code>shared:check</code></td><td data-id="c4b2">green, 4 vendoring skills</td></tr>
  <tr data-id="c4r3"><td data-id="c4a3"><code>drift:check</code></td><td data-id="c4b3"><strong>RED on 2 pre-existing files — not from this branch</strong></td></tr>
  <tr data-id="c4r4"><td data-id="c4a4"><code>fixtures:check</code></td><td data-id="c4b4">green (96 json, 10 asserters)</td></tr>
  <tr data-id="c4r5"><td data-id="c4a5"><code>fixtures:assert</code></td><td data-id="c4b5">green, both trees (6 golden, 4 smoke)</td></tr>
  <tr data-id="c4r6"><td data-id="c4a6"><code>lint:model-ids</code></td><td data-id="c4b6">green</td></tr>
  <tr data-id="c4r7"><td data-id="c4a7"><code>lint:md</code> / <code>fmt:check</code></td><td data-id="c4b7"><strong>UNVERIFIED</strong> — dprint + markdownlint absent, npx cannot fetch offline</td></tr>
  <tr data-id="c4r8"><td data-id="c4a8"><code>heroku-eb-runtime-settings.test.ts</code></td><td data-id="c4b8">7 pass / 5 fail, <strong>pre-existing</strong>, needs the <code>terraform</code> binary</td></tr>
</table>

### Blocker still needing an owner — three sessions old

`drift:check` fails on `skills/gcp-to-aws/SKILL.md` and `skills/heroku-to-aws/SKILL.md`. **Predates this branch.** Telemetry landed advisor-only: `migrate/plugins/migration-to-aws` has **no `hooks/` directory**, so the advisor copies carry a frontmatter `hooks:` block and a consent section the migrate copies cannot (the hook command would resolve to a nonexistent file, and the emitter-path search pattern names the advisor plugin, which is not a normalized token class). Deliberately **not** allowlisted — it is someone else's drift. The fix is two `ALLOWLIST` entries; the reasoning is already written as a comment above the `azure-to-aws` entry.

**Also run before any PR:** `mise run fmt` (dprint re-pads markdown tables; ours are hand-aligned) and `gitleaks`.

***

## 9. Where to go next

<table data-id="c5" data-col-sizes="300,400">
  <tr data-id="c5r0"><th data-id="c5h0">Step</th><th data-id="c5h1">State</th></tr>
  <tr data-id="c5r1"><td data-id="c5a1">0 · shared promotion + <code>run_mode</code></td><td data-id="c5b1"><strong>done</strong></td></tr>
  <tr data-id="c5r2"><td data-id="c5a2">1 · backbone skeleton</td><td data-id="c5b2"><strong>done</strong></td></tr>
  <tr data-id="c5r3"><td data-id="c5a3">2 · discovery breadth</td><td data-id="c5b3"><strong>partial</strong> — Terraform done. Remaining: Bicep, ARM, billing, app-code, RDfA, then live <code>az</code> (security contract → capture pre-work → parsing fragment, in that order)</td></tr>
  <tr data-id="c5r4"><td data-id="c5a4">3 · mapping algorithm</td><td data-id="c5b4"><strong>done</strong> (pass 1)</td></tr>
  <tr data-id="c5r5"><td data-id="c5a5">4 · clustering + patterns</td><td data-id="c5b5">not started — corpus already holds the merge and split cases; parallelizes with 5</td></tr>
  <tr data-id="c5r6"><td data-id="c5a6">5 · content depth</td><td data-id="c5b6">not started. <strong>Start with <code>compute.md</code> + <code>database.md</code> only</strong> — the two the corpus tests</td></tr>
  <tr data-id="c5r7"><td data-id="c5a7">6 · estimate / generate / workshop</td><td data-id="c5b7">not started</td></tr>
  <tr data-id="c5r8"><td data-id="c5a8">7 · fixtures</td><td data-id="c5b8">partial — Discover and Design pass-1 oracles exist</td></tr>
</table>

### Three decisions waiting

1. **The `drift:check` blocker** (§8) — needs the telemetry branch's owner, or a call to allowlist.
2. **A completed-Design golden needs a variant inventory.** The STOP case and completion are **mutually exclusive on this corpus**: `azurerm_dev_test_lab` always halts. `after-design-complete/` therefore needs an inventory with `iac_metadata.untranslated_types` cleared — the state *after* the user files the type. One field, one extra committed file, but it needs deciding rather than discovering.
3. **How to test Clarify** (§7) — the interactive-phase gap.

***

## 10. Traps that will bite a fresh session

- **Every skill edit is a TWO-TREE edit.** Forget the mirror and `drift:check` fails.
- **`lint:frontmatter` passing means nothing if the count is 0.** Always read the count.
- **`_assert` has no teeth.** Do not add a rule there and consider it enforced. `generate.md`'s `run_mode` consent check is an `_assert` and says so in its own prose.
- **A hand-authored golden drifts from a prose-only ref, by construction.** This bit twice in one session, in opposite directions: `extract-terraform.md` was missing rows the golden had, and `design-infra.md` was missing fields the oracle asserted. **If the oracle asserts it, a skill file must require it.** That is what `schema-design-aws.md` exists to prevent.
- **Keep `index.md`'s candidate sets unordered and default-free.** The moment a default appears there, the halt guard is bypassable.
- **zsh, not bash.** Unquoted `$var` does not word-split. `$VAR:h` is a history modifier.
- **`emit.mjs` needs a hook payload on stdin** or it throws (fail-open, so harmless, but zero telemetry with no signal).
- **gitleaks runs over this repo.** Never put a realistic credential in a fixture — the sentinel is `FIXTURE_SENTINEL_MUST_NOT_APPEAR`.
- **x86_64 default, not Graviton.** Deliberate; Windows/.NET prevalence. It will look like a bug.
- **App Runner is banned**, including in trigger text and candidate lists.
- **Unfixed, known:** most `azure_id` values carry a `tf:<local>` name segment because the corpus names everything with `${var.prefix}`, so they are not real ARM IDs and cannot be matched against a live capture. Now flagged by the `name_expression_unresolved` warning (one entry per run). The fix — a per-resource `azure_id_synthetic` marker — belongs with the live `az` path, where the drift comparison it protects actually happens.
