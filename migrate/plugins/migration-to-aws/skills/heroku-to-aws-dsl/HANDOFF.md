# heroku-to-aws-dsl — Handoff

_Last updated: 2026-06-29. Branch: `feat/heroku-dsl-refactor` (15 commits ahead of
`origin/main`; nothing pushed). `mise run build` green. UNCOMMITTED this session:
the `ref-resolve` cross-unit check (+`REF_RESOLVE`/`JSON_INVALID` codes,
`node-shims` `statSync`) and the reproducibility findings below — 6 working-tree
files, not yet committed._

> This handoff has two halves: **Part A** — the DSL skill itself (all 6 phases,
> authored + cold-LLM validated). **Part B** — the **TypeScript conformance
> validator** (a complete typed parser + check suite that replaced the original
> Python validator). Part B is the bulk of the most recent work.

---

## What this is

A **third** expression of the heroku-to-aws migration skill, alongside:

- `skills/heroku-to-aws/` — upstream **pure markdown** (on `main`); the source of
  truth for WHAT each phase must do.
- the **MCP engine** refactor (`feat/heroku-mcp-refactor`) — deterministic logic
  in Python tools + JSON.
- **this** (`skills/heroku-to-aws-dsl/`) — a declarative **phase DSL the LLM
  interprets at runtime**. NO engine, NO server. CI validates the DSL structure
  statically; the LLM enforces pre/postconditions at runtime by reading them.

Core principle: **structure is checkable (DSL), judgment is the LLM's (prose).**
A DSL makes STRUCTURE checkable but does NOT make ARITHMETIC deterministic — the
clamp/sizing/cost-math leaves are isolated to specific phases (design, estimate)
and demoted to labeled provenance so nothing invites re-derivation.

## Read-first orientation

| Read                         | Why                                                                                                             |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `INTERPRETER.md`             | the shared DSL vocabulary (the closed `_`-key grammar). **The single source of truth the type system mirrors.** |
| `docs/unit-taxonomy-spec.md` | the Phase/Fragment/Assembler taxonomy + conformance checklist                                                   |
| `docs/dsl-types.md`          | **the canonical type-system model** (the formal grammar; Part B's spec)                                         |
| `SKILL.md`                   | skill entry point                                                                                               |
| this file                    | current state + how to resume                                                                                   |

---

## Part A — The DSL skill (all 6 phases DONE)

| Phase        | State                                                                                                                                                                                      | Verdict                                                                                                                                                                            |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **discover** | ✅ authored, refactored to the unit taxonomy, cold-LLM validated (incl. billing + re-entry)                                                                                                | `test-output/discover-report.md`, `discover-3kind-refactor-verdict.md`, `discover-routes-refactor-verdict.md`, `discover-upstream-coverage-audit.md`, `reentry-cascade-verdict.md` |
| **clarify**  | ✅ 1 fragment (interview) + no-op/validator assembler; question set extracted to `knowledge/clarify/clarify-questions.json` (data-driven driver); `preferences.schema.json`                | `test-output/clarify-verdict.md`                                                                                                                                                   |
| **design**   | ✅ 1 mapping fragment + validator assembler (route gates) + EKS branch fragment; 7 `knowledge/design/*.json` tables; `aws-design.schema.json`. The first MATH-bearing phase.               | `test-output/design-arithmetic-probe.md`, `design-verdict.md`, `eks-verdict.md`                                                                                                    |
| **estimate** | ✅ 1 cost-engine fragment + validator assembler; `knowledge/estimate/{aws-pricing,estimate-defaults}.json`; `estimation-infra.schema.json`. EKS-aware, cache+optional-MCP.                 | `test-output/estimate-arithmetic-probe.md`, `estimate-verdict.md`                                                                                                                  |
| **generate** | ✅ MULTI-ARTIFACT: 3 fragments (terraform + docs + eks-generate) + cross-artifact validator assembler; `templates/generate/**`; `generate-routing.json`; `generation-warnings.schema.json` | `test-output/generate-verdict.md`, `eks-verdict.md`                                                                                                                                |
| **feedback** | ✅ TERMINAL: 1 collect fragment + validator assembler; `feedback-config.json` + `feedback{,-trace}.schema.json`; `_advances_to: complete`                                                  | `test-output/feedback-verdict.md`                                                                                                                                                  |

### Real-repo end-to-end

`test-output/real-repo-run-verdict.md` — a clean discover→generate run against a
real large-terraform sample repo. **Caught + fixed the RDS pricing coverage gap**
(commit `6225fd4`) — the defect that the validator's XTABLE check now guards
against automatically.

### The DSL architecture (three unit kinds)

See `docs/unit-taxonomy-spec.md` for the full spec. In brief:

- **Phase** — lifecycle + composition. `_fragments` (ordered) + `_assemble`
  (mandatory). ZERO `## Step:` sections (work is in the units).
- **Fragment** — ONE responsibility → 1..N artifacts written directly to disk.
  Never reads another fragment's output. One-or-more steps.
- **Assembler** — exactly one per phase, terminal. `_reads`/`_mutates`/`_produces`
  to combine/enrich fragment outputs. The only mutator.

Key rules: creator/mutator ownership (last writer owns final postconditions);
`_re_entry_guard` is a top-level pre-steps phase key; closed `_`-vocabulary in ALL
unit files; trigger lives in the phase's `_fragments` list; knowledge/contract/
procedure separation (constants → `knowledge/`, output shape → `schemas/`,
algorithm → step prose, output skeletons → `templates/`); unit-file region grammar
(frontmatter → H1 → one `## Orientation` → `## Step:`*, nothing else).

### `test-output/` — index of every verdict

All are **cold-LLM verdicts**: a fresh Claude Code subagent with zero repo
context, read-only sandbox, computed artifacts + a harsh defect report, graded
against hand-computed expected values.

| File                                  | What it validates                                                                                                 |
| ------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `discover-report.md`                  | base discover executability (Form 2b + billing)                                                                   |
| `reentry-cascade-verdict.md`          | re-entry halt + cascade-on-confirm; caught the guard-evaluated-too-late bug                                       |
| `discover-routes-refactor-verdict.md` | the interim routes refactor (superseded by 3-kind)                                                                |
| `discover-3kind-refactor-verdict.md`  | the final Phase/Fragment/Assembler taxonomy PASS                                                                  |
| `discover-upstream-coverage-audit.md` | confirmed nothing dropped vs upstream's 3 discover files; restored 2 gates                                        |
| `discover-inventory.actual.json`      | the actual inventory a cold run produced (artifact, not a verdict)                                                |
| `clarify-verdict.md`                  | clarify port PASS; fixed Q5b/Q6b dup, unreachable flag, timestamp source                                          |
| `design-arithmetic-probe.md`          | pre-authoring probe: design math = lookup + 0–100 clamp + tier branches; threat is RE-DERIVATION                  |
| `design-verdict.md`                   | design port PASS on two fixtures (incl. a hard one); the DSL thesis HOLDS for the math phase                      |
| `eks-verdict.md`                      | the EKS cross-phase pass (design + generate branches)                                                             |
| `estimate-arithmetic-probe.md`        | caught the multi-AZ convention hazard (rds baked-in vs elasticache ×2 vs aurora intrinsic)                        |
| `estimate-verdict.md`                 | estimate port PASS end-to-end                                                                                     |
| `generate-verdict.md`                 | generate PASS; caught + fixed an apply-blocking dangling-SG defect; added reference-integrity gates               |
| `feedback-verdict.md`                 | feedback PASS; fixed un-observable share trigger, pinned plugin-version resolution, tightened trace anonymization |
| `real-repo-run-verdict.md`            | clean real-repo discover→generate; caught the RDS pricing coverage gap                                            |

---

## Part B — The TypeScript conformance validator (COMPLETE, live in build)

A complete **typed parser + check suite** that validates a whole skill. Built as a
disciplined modeling exercise: model the DSL grammar as types, parse real files
into those types, then check the rules the types can't express. **Replaced** the
original Python `scripts/validate_dsl.py` (superseded; still on disk, retire in a
follow-up).

**Canonical model:** `docs/dsl-types.md` (~1000 lines) — language-agnostic prose +
type sketches, the single source the TS code answers to. Records the drift
contract, the four type tiers, every discovered nuance/spec-gap, the toolchain
conventions, and the parser/check-layer design.

**Runs as:** `mise run lint:dsl` → `node scripts/dsl-validator/validate.ts <root>`
→ reports `22 unit files / OK`. Type-checked by `mise run lint:types`
(`tsc --noEmit` strict). Both wired into `mise run build`.

### Layer map (`scripts/dsl-validator/`)

```
validate.ts            ← orchestrator + CLI: discover -> bind -> check -> report -> exit
tsconfig.json          ← strict, esnext/bundler, allowImportingTsExtensions (no package.json)
node-shims.d.ts        ← hand-written node:fs/process ambient decls (keeps zero-dep)
findings.ts            ← Finding (severity + closed FindingCode + location), Result<T>

types/                 ← the type system — 14 types, 4 tiers (mirrors docs/dsl-types.md)
  error-action.ts when-condition.ts check-verb.ts trigger.ts        (Tier 1: atoms)
  condition.ts guarded.ts fragment-ref.ts re-entry-guard.ts
    on-error-table.ts assembler-ref.ts                              (Tier 2: entries)
  meta.ts step.ts orientation.ts frontmatter.ts                     (Tier 3: sub-docs)
  unit.ts                                                           (Tier 4: the apex)

parser/                ← pure syntax
  yaml.ts              ← hand-written YAML-subset reader (zero deps)
  split.ts             ← file -> frontmatter + H1 + Orientation + Step regions

binders/               ← YamlValue -> typed types (bottom-up; Result-based)
  shared.ts (helpers + bindList) error-action when-condition check-verb trigger
  condition guarded fragment-ref re-entry-guard on-error-table assembler-ref
  meta step orientation frontmatter unit

checks/                ← typed Unit -> Findings (semantic / cross-reference)
  check.ts             ← IntraUnitCheck/CrossUnitCheck + runChecks + UnitIndex
  regions uses assert-post-only interlock                          (intra-unit)
  fragment-ref subset guard-scope produces phase-chain xtable      (cross-unit)
```

### What each check enforces

**Bind-time (the binders emit):** `CLOSED_VOCAB` (unknown `_`-key), `FORM1_LEAK`
(`_cases`/`_default`/`_steps` in a 2b meta block), `BIND` (shape mismatch), `YAML`
(malformed frontmatter/meta).

**Intra-unit:** `regions` (phase=0 steps, frag/asm≥1), `uses` (every `[_uses:F]` ∈
step meta), `assert-post-only`, `interlock` (re-entry action must be STOP).

**Cross-unit:** `fragment-ref` (refs resolve: file/kind/`_of_phase`/id), `subset`
(step files ⊆ owning-phase `Guarded` — single-load-owner), `guard-scope` (warn: a
`_when` naming a produced-not-input artifact), `produces` (ownership identity,
exempting assembler-`_reads` intermediates + directory-prefix coverage),
`phase-chain` (`_advances_to`/`_requires_phase` consistency), `xtable`
(producer-emits ∈ consumer-keys — the RDS-gap catcher, regression-verified),
`ref-resolve` (every `_validate_schema`/`_knowledge`/`_templates` ref resolves to
an on-disk file; referenced knowledge/schema JSON parses; orphan-knowledge sweep —
codes `REF_RESOLVE`/`JSON_INVALID`/`ORPHAN`; added 2026-06-29, see
`docs/dsl-types.md` → "COVERAGE GAP CLOSED").

### Toolchain (documented in `docs/dsl-types.md` → "Toolchain conventions")

TS runs via **Node 24 native type-stripping** (zero npm deps to run) and is
type-checked by **`tsc --noEmit`** (`npm:typescript` via mise, dev-time only). Five
coexistence rules: (1) inline `type` imports, (2) `.ts` import extensions +
`allowImportingTsExtensions`, (3) `esnext`/`bundler` module resolution (no
`package.json`), (4) NO TS parameter properties (strip-only rejects them), (5)
`node:` API users need ambient decls — supplied by `node-shims.d.ts`, not
`@types/node`.

### Model corrections the evidence-driven build surfaced (the payoff)

Building types from the spec and verifying against **real files** caught four real
errors that prose review would have missed — all recorded in `docs/dsl-types.md`:

1. `_unrecoverable` carries a message (Type-1 model was wrong; `tsc` rejected the
   bad probe — message is optional on the two STOP variants).
2. `_steps` spec-gap: INTERPRETER's prose under-lists `_templates`/`_reads`/
   `_mutates` and over-lists `_cases`; types modeled from the REAL meta vocabulary.
3. `_writes` is list-or-scalar (caught when `bindUnit` hit `generate-docs.md`).
4. `produces` ownership rule was too literal (missed assembler-`_reads`
   intermediates + directory-prefix coverage); refined against the real DSL.

Plus the YAML multi-key-precondition indentation bug (caught parsing
`design.phase.md`).

---

## Reproducibility findings (cold-run experiment, 2026-06-29)

Ran the skill end-to-end as the LLM-interpreter against two sample repos, then
ran each repo TWICE in fully-isolated **cold** subagents (`gpu-dev`, zero shared
context, separate `.migration/COLDRUN-A|B` dirs) and diffed the outputs. Goal: is
the skill reproducible run-to-run? Repos:
`sample-repos-heroku-aws-migration/{medium-terraform-billing, medium-terraform-with-app-json}`.

**Headline: the DECISION is reproducible; some leaf VALUES are not.** Across all
runs the service mapping (dyno→Fargate sizing, pg→RDS class, redis node type,
fast-path service identity), service COUNT, complexity TIER, and the RECOMMENDATION
path were identical. The thesis holds: deterministic table lookups + clamps are
stable. What drifted are under-specified leaves the schema/tables leave open —
exactly the residual-judgment surface the design docs predicted.

**Timing (cold vs cold):** repo 1 = 502s vs 507s (~1%); repo 2 = 520s vs 422s
(~19%). Cold-run time tracks TOOL-CALL count (how much the interpreter reads /
re-derives / self-corrects), NOT a property of the skill (which has no runtime).
Not a meaningful skill metric; recorded only to debunk the warm-context "second
run is faster" artifact (warm reuse ≠ cold cost).

**Three reproducibility gaps surfaced (NOT yet fixed) — see debt items below:**

1. **Standard-SG ingress CIDR is a run-to-run coin-flip** (highest priority —
   security-relevant). The standard (non-Private-Space) SG `app_https`/`app_http`
   inbound `cidr` came out `0.0.0.0/0` in some cold runs and `10.0.0.0/16`
   (the VPC CIDR) in others — and the flip went OPPOSITE directions on the two
   repos, so neither agent is consistently right. `design-defaults.json`
   `security_group.default_inbound_cidr` IS `0.0.0.0/0` (the intended value);
   the design-mapping prose doesn't pin it tightly enough. Fix: tighten the
   `design_vpc` step prose to force `default_inbound_cidr` for the default SG, and
   add a design `_assert` / validator check pinning it.

2. **Fast-path flat-cost estimates are unpinned** (cost reproducibility). On the
   app.json repo, the SES line came out $1.00 vs $5.00 across cold runs → total
   $623.63 vs $627.63 (~0.6%). Root: `aws-pricing.json.fast_path_services.ses`
   says "flat minimal baseline" with NO concrete monthly figure; `amazon_mq`/
   `opensearch` use `instance_monthly_est` but `ses`/`eventbridge`/`s3`/
   `cloudfront`/`secrets_manager` have only per-unit rates + a prose "minimal"
   instruction → the LLM guesses. Repo 1 had no fast-path addon, so it was
   penny-identical; this only bites stacks WITH fast-path-priced addons. Fix: give
   each fast-path service a concrete `monthly_baseline_est` the formula reads.

3. **`estimated_db_size_gb` source is inconsistent.** For `postgres standard-2`
   one cold run wrote `256` (the sizing table's `storage_gb`, correct for
   `db_size_source: plan_derived`), another wrote `10` (looks like it grabbed the
   Q6c "<10GB→pg_dump" size HINT instead of the plan storage). Both ran
   `plan_derived`, so `10` is wrong. No recommendation impact, but a
   downstream-readable field is unstable. Fix: clarify in clarify-interview /
   design that `estimated_db_size_gb` under `plan_derived` MUST be the sizing
   table `storage_gb`, not the Q6c hint bound.

**Also reconfirmed (schema-flexible, NOT bugs):** `preferences.json` shape varies
(flat sectioned vs an `answers[]` array; `clarify_mode` full vs fast_path though
all-defaults were applied either way); `financial_summary`/optimization key naming
and `percent_change` rounding differ; key ordering differs. All schema-valid and
decision-equivalent — the validator accepts them, which is correct. Pinning these
is optional (would only matter for byte-diff snapshot testing).

The four run dirs are left on disk under each repo's `.migration/` if needed for
inspection; they are gitignored (not part of the skill).

---

## External grammar review (2026-06-29) — verdict + root-cause reframe

A fresh zero-context Kermes session reviewed the grammar (review at
`.agents/scratchpad/dsl-grammar-design-review-2026-06-29.md`). Verdict: design is
sound; thesis (structure checkable, judgment LLM's, arithmetic isolated) largely
holds. Spot-checked its load-bearing claims against the files — **all verified**.

**The reframe (better than our 3-separate-bugs framing):** the three
reproducibility gaps above are ONE structural gap, not three. There is an
UNNAMED third category between "structure" and "judgment": **values deterministic
IN INTENT but pinned only IN PROSE inside knowledge JSON** (e.g.
`include_port_when: "always (app ingress)"`, `restricted_cidr_source: "...if
present, else the VPC/app CIDR"`, `ses.formula: "flat minimal baseline"`). Nothing
— schema, `_assert`, or validator — can pin them, and the grammar has NO
vocabulary to express a value-pinning invariant statically. "Isolation ≠ pinning":
knowing where the math is doesn't make it reproducible. Closing this STRENGTHENS
the thesis (it separates genuine narrative judgment from under-specified
determinism), it doesn't contradict it.

**New findings beyond our three (verified, NOT yet fixed):**

- **[review 2A] `restricted_cidr_source` is prose-valued — HIGH (security,
  latent).** Verified `design-defaults.json:35` is an English conditional; the
  Private-Space path, even less pinned than the SG-CIDR coin-flip, and cold runs
  never exercised it (no Private-Space fixture). Fix: structured selector
  `{primary, fallback}` + a design `_assert`.
- **[review 3B] unit-taxonomy-spec OVER-CLAIMS enforcement — MED (doc defect).**
  Verified `unit-taxonomy-spec.md:240-241` says knowledge-separation checks 9–12
  are "ENFORCED by `scripts/validate_dsl.py`" — the RETIRED Python validator; the
  live TS validator has NO `BARE_LITERAL`/`DUPLICATION` code. Either port the
  heuristics into TS (new codes) or downgrade the spec language to "convention."
- **[review 1A] in-run state (`_writes_var`/`_collect`/`_for_each`) has no
  scope/lifetime/visibility model — HIGH.** Works today only because accumulators
  happen to be treated phase-scoped (design-mapping `_collect: [...spaces]` read
  cross-step by `design_vpc`), but INTERPRETER never states it. Two faithful
  interpreters can disagree. Fix: add the state model + a declared-before-read
  check.
- **[review 1B] `_branch_on` + prose case-arms is unverifiable — MED.** Structured
  discriminant, BOLD-PROSE arms (design-mapping formation/addon/pipeline/space);
  nothing checks the arms cover the value-set — the EXACT silent-drop class that
  bit the old `design.py`. Fix: optional `_cases:[...]` labels for a coverage
  check.
- **[review 2B] redis `engine_version` unpinned** while postgres IS
  (`engine_versions.rds_postgresql: "15"`, no `elasticache_redis` sibling) — MED.
- **[review 2C] `service_count` definition drift** feeds deterministic
  metrics/alarms math: `observability_cost` uses it unqualified while
  `comparison_roi_complexity` defines it as `metadata.total_services` (which
  INCLUDES ALB entries) — MED. Canonicalize once.
- **[review 4A] "intermediate artifact" is a real 4th category** handled by
  validator EXEMPTION not model (fragment `_produces` ∩ assembler `_reads`, ∉ phase
  `_produces` — e.g. `_eks-design.json`, `billing-profile.json`). Promote to the
  taxonomy model — MED.
- Plus LOW items: `_input` glob-vs-artifact overload (1C), `_validate_schema`
  dialect/strictness unspecified (1D), inverse re-entry guard-scope unchecked
  (1E), Property-16/`total_services` asserts are tautological self-checks (3B),
  `XTABLE` links hand-maintained (3C — already in debt), duplicate `_assert`
  across postcondition levels (5A), `on_confirm` cascade vs downstream `_produces`
  uncheckable (5B — parked in dsl-types), no `_interpreter_version` stamp so a
  CHANGED (vs added) key won't fail closed (5D).

**Review's top-5 priority (its ranking, endorsed):** (1) pin every deterministic
leaf to a concrete value + add a lint heuristic flagging prose-valued determinism
(`/flat|minimal|compatible with|if present, else|approximate|UPPER-BOUND/` in
pinned fields — same spirit as the existing literal-in-step-prose heuristic);
(2) specify the in-run state model + declared-before-read check; (3) build the
parked cross-phase checks (`on_confirm` cascade == ⋃ downstream `_produces`;
inverse guard-scope); (4) reconcile the over-claimed enforcement (3B); (5) make
`_branch_on` coverage checkable + name the intermediate-artifact category.

---

---

## Known debt / decisions for next session

- **[repro] DONE (Track A, 2026-06-29).** All three cold-run reproducibility gaps
  fixed + the structural-completeness asterisk closed. Specifically:
  - redis `engine_version` pinned to `design-defaults.engine_versions.elasticache_redis: "7.0"` (was "compatible with…" prose).
  - `restricted_cidr_source` converted to a structured `{primary, fallback}` selector with exact field-paths (was the ambiguous "…else the VPC/app CIDR" noun).
  - SG ingress CIDR + redis engine now PINNED by `_assert`s in `design-assemble` (the coin-flip is now a fail-closed gate, not a hope).
  - Q6c `estimated_db_size_gb` split from the method-choice threshold (now pinned to the sizing-table `storage_gb` under `plan_derived`).
  - `service_count` canonicalized to `metadata.total_services` in the estimate observability math.
  - fast-path stopgap costs (ses/eventbridge/s3/cloudfront/secrets) pinned to concrete `monthly_baseline_est` literals flagged as stated assumptions (`_basis`) — external pricing will replace these wholesale.
  - `_branch_on` coverage gap CLOSED: new `_branch_cases` meta key (declares the discriminant values prose arms cover) + a `BRANCH_COVERAGE` validator check (defect-probe-verified). The structural-completeness claim now has no asterisk.
  - unit-taxonomy-spec over-claim FIXED (it cited the retired `validate_dsl.py` as enforcer of checks the TS validator doesn't implement; now correctly marks items 1-3 as conventions).
  - INTERPRETER `_branch_on` doc corrected to FORM-2b reality (prose arms + `_branch_cases`, not the FORM-1 `_cases` map).
- **`mise.toml` is admin-owned** (`@awslabs/startups-admins`) and was CHANGED this
  arc (lint:dsl → TS, +`npm:typescript`, +`lint:types`). Flag for their review on
  merge.
- **Retire the Python `scripts/validate_dsl.py`** — superseded by the TS validator,
  still on disk.
- **INTERPRETER spec fixes** (from Part B findings): update the `_steps` section to
  list `_templates`/`_reads`/`_mutates` and mark `_cases`/`_default`/`_steps` as
  FORM-1-only.
- **`migration_urgency`** clarify fast-path field — no schema property, untested;
  add to schema or drop.
- **Before merge:** repoint any forked `.mcp.json`/source pins to upstream.
- **`on_confirm` is spec-fuzzy** (named reset vs inline artifact list) — a
  candidate for spec tightening; modeled permissively for now.
- **XTABLE's producer→consumer links are a manual list** in `checks/xtable.ts` —
  the one spot whose own coverage can silently rot if a new sizing→pricing table
  is added without declaring its link.
- Re-entry "explicit confirmation" prompt/token is still undefined.
- `line_item_csv` billing format detected but unparsed — INHERITED from upstream,
  NOT a regression; do not invent parse logic.

## How to resume

1. Read `INTERPRETER.md` + `docs/unit-taxonomy-spec.md` + `docs/dsl-types.md`.
2. Run `mise run lint:dsl` and `mise run lint:types` — both should be green
   (`22 unit files / OK`).
3. The skill (Part A) and the validator (Part B) are both complete. Likely next
   work: the debt items above, or pushing the branch to `fork`
   (`git push fork feat/heroku-dsl-refactor`) — push target is the personal fork,
   NEVER `origin` (upstream awslabs/startups).
4. For any DSL change: update `docs/dsl-types.md` + the matching `types/` +
   `binders/` in the SAME change (the drift contract — the validator rejects
   unknown `_`-keys, so an unmirrored addition fails loudly on first use).
