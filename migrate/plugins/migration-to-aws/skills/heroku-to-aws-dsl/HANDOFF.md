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
- **`_re_entry_guard` sub-key naming wart** (grammar uniformity) — its children
  are BARE and idiosyncratic (`if`, `action`, `reason`, `on_confirm`) on TWO
  axes: `if` is a one-off spelling of what is semantically a `_when` (same
  `WhenCondition` type), and none of the sub-keys carry the `_` prefix that every
  other composite's sub-keys use (`_fragments`' `_id`/`_trigger`/`_file`). It is
  the one place the closed-vocab `_`-prefix convention breaks. No runtime impact
  (the binder reads `if`, maps it to `WhenCondition`, the LLM evaluates it like
  any guard), but it weakens the "a `_`-key IS the recognizable structural token"
  invariant and forces the LLM-interpreter to learn the re-entry condition as a
  distinct thing rather than "another `_when`." `dsl-types.md` records it as an
  INCONSISTENCY ("recorded; does not change the type"). Fix: rename to
  `{_when, _action, _reason, _on_confirm}` for uniformity (mechanical rename
  across the type field, binder, INTERPRETER.md, and the one usage in
  `discover.phase.md`); cosmetic-correctness, not behavioral, so fold into the
  next grammar pass. Would also enable a future "structural sub-keys must be
  `_`-prefixed" check that nothing enforces today.
- **XTABLE's producer→consumer links are a manual list** in `checks/xtable.ts` —
  the one spot whose own coverage can silently rot if a new sizing→pricing table
  is added without declaring its link.
- Re-entry "explicit confirmation" prompt/token is still undefined.
- `line_item_csv` billing format detected but unparsed — INHERITED from upstream,
  NOT a regression; do not invent parse logic.
- **Position-2 prose error-actions have no `[_uses:]`-style tether** (grammar
  consistency + closed-vocab anchoring). `ErrorAction` appears in THREE positions:
  (1) `_on_failure` on a condition (structured, checkable); (2) MENTIONED IN STEP
  PROSE as a parenthetical/verb (a parenthesized warn-and-skip token in design-mapping.md
  map_resources, or `_defer` written as the verb in the addon branch); (3) the
  `_on_error:` documentation table. Position 2 is the gap: the action token is
  prose DECORATION, not a reference — nothing checks it is a valid
  `ErrorActionKind` or that it is declared in this unit's `_on_error` table. This
  is an ASYMMETRY: the SIBLING problem (a closed-vocab thing named in prose) is
  already solved for FILE references by the uses-marker, but actions got
  no equivalent. FIX (minimal, modeled on the uses-marker): an inline action
  marker (action-tag carrying the token) replacing the bare parenthesized token;
  reads identically, but a new check (`ACTION_REF`) verifies (a) closed-vocab,
  (b) the action is declared in the unit's on-error table, (c) optional: a STOP
  action inside a for-each body warns (control-flow mismatch). Mechanically a
  near-clone of `checks/uses.ts` + a `Step.actions` projection like `uses`.
  CRITICAL BOUNDARY -- do NOT lift error POLICY into a structured error-rules
  block: the error branches ARE the algorithm (interleaved with the lookup/clamp
  steps), and extracting them fragments the procedure (violates the
  knowledge/contract/procedure readability guardrail). Tether the TOKEN inline;
  leave the condition + message + placement as prose. Also requires the
  untagged-action drift rule (a bare backticked action token in prose that is NOT
  action-tagged is a violation -- exactly as `uses` flags untagged file
  backticks), else authors just don't tag and nothing is gained. Five-place drift
  contract applies (Step type, binder extraction, INTERPRETER.md, dsl-types.md,
  new check+FindingCode) + migration churn (dozens of existing prose mentions).
- **`_on_error` documentation table duplicates canonical semantics with NO drift
  check** (no-duplication, error layer). Every unit's `_on_error:` block restates
  each action's `{effect, status}` (e.g. discover.phase.md:90
  `_halt_and_inform: { effect: "stop; surface diagnostic", status:
  retain_in_progress }`) — the SAME canonical meaning re-typed by hand across
  ~10+ units. Nothing checks these match the canonical `ERROR_ACTION_SEMANTICS`
  table in `types/error-action.ts`; a unit could typo `_halt_and_inform`'s status
  as `revert_to_pending` and pass green. This is the no-duplication rule violated
  in the error layer (same class as the estimate formula duplication). It is also
  a LISTED-BUT-UNBUILT "validation power this unlocks" note in dsl-types.md Type 11
  (`OnErrorTable`). FIX: a check comparing each `OnErrorTable` entry's
  `{effect,status}` against `ERROR_ACTION_SEMANTICS` (the canonical source per
  INTERPRETER.md line 165), OR — better — stop re-typing it: make `_on_error`
  declare only WHICH actions the unit uses (a name list) and let the canonical
  table own the `{effect,status}`, removing the duplication at the source.
- **NEW DOC (planned, capstone deliverable): top-down narrative on-ramp.** A
  THIRD doc above `docs/dsl-language-guide.md`, for a teammate who has never
  opened the files. Tells the story in COMPREHENSION order (migration → phase →
  fragment/assembler → the frontmatter contract keys → descend to leaves like
  `_when`/`ErrorAction`/`Trigger` as they ARISE), motivated by need. Rationale:
  leaf nodes are defined by their CONTEXT OF USE, not their shape — `_when` is a
  trivial string whose entire interest is WHERE it sits and WHAT it gates, so it
  is meaningless cold but obvious once the phase that contains it is on the
  table. The three-layer stack: (1) this top-down narrative = "what is this, why,
  where do I look"; (2) `dsl-language-guide.md` (bottom-up tiers) = grammar+type+
  binding per construct; (3) `dsl-types.md` (bottom-up canonical) = the spec.
  HARD CONSTRAINT to prevent the 3-doc drift trap (cf. the stale
  `validate_dsl.py` over-claim): the new doc OWNS NARRATIVE ONLY (motivation,
  ordering, connective tissue) and must NOT restate any fact that lives
  authoritatively elsewhere — NO type signatures, NO closed `_`-key vocab, NO
  binding examples, NO check names. The moment it needs one, it LINKS DOWN to the
  guide/spec instead of copying. Litmus test per paragraph: "is this fact also in
  the guide/spec?" yes → link; pure motivation/sequencing → belongs here. Top-
  down tolerates forward references (a human reads linearly with a teacher's
  framing); the spec can't, which is WHY they stay separate docs. Requires
  `dsl-language-guide.md` sections to have stable, clean heading anchors as link
  targets (mostly true — numbered sections — verify on build). SEQUENCING: author
  this LAST, after the construct-by-construct deep-dive, so it DISTILLS the
  accumulated motivation (e.g. the `_when` "four contexts / one shape / why
  INTERPRETER.md explains it four times" thread is exactly the connective tissue
  it wants) rather than being written ahead of the understanding.
- **Resolution-class field metadata** (legibility + enforcement-gap finder) —
  make the build-time-checked vs LLM-runtime-interpreted boundary a FIRST-CLASS,
  visible fact. Today it is implicit/tribal: you must know that
  `WhenCondition.condition` and `_assert`'s `condition` are opaque to CI (LLM
  evaluates them) while `ValidateSchema.schema` IS resolved at build time. The
  boundary bisects several types FIELD-BY-FIELD (e.g. `Condition.verb` is
  build-time/closed-set but its `_assert` `condition` payload is LLM; `Guarded`
  `file` is REF_RESOLVE'd but `when` is LLM; `ReEntryGuard` `action` is
  build-time but `if` is LLM). Do NOT add a per-instance field on the value type
  (the mode is CONSTANT per field — `WhenCondition` is ALWAYS llm — so an
  instance tag carries zero info and muddies the "types are pure shape" rule).
  Instead: (A) adopt a closed `@resolution` JSDoc vocabulary on each FIELD —
  `build-time` (CI fully checks), `build-time-partial` (CI checks shape/existence
  not correctness), `llm-runtime` (opaque; LLM evaluates), `cosmetic` (no
  meaning, e.g. H1 title); (B) derive a per-field matrix in
  `docs/dsl-language-guide.md` (field × resolution-class × the enforcing
  `FindingCode`, or "none — LLM"). The matrix DOUBLES as an enforcement-gap
  finder: any field tagged `build-time` with NO check is a documented-but-
  unenforced gap (would systematically surface the `_assert`-body and
  formula-duplication holes the review found by hand). Optional (C, expensive):
  a meta-check asserting every `build-time` field names a check. Start with A+B.
  NEXT STEP: draft + pressure-test the 4-class `@resolution` vocabulary against
  the tricky mixed types (`Condition`, `ReEntryGuard`, `Meta`) before tagging.
  WORKED EXAMPLE — `Trigger` is the CLEANEST case for this work: its five forms
  ALREADY split mechanical-vs-judgment along the existing token discriminant —
  `_always`/`_glob`/`_artifact_exists`/`_check_source_exists` are
  `deterministic-runtime` (a file is there or it isn't; two faithful runs always
  agree), while `_when` is `llm-runtime` (opaque prose judgment). The grammar
  thus DERIVABLY differentiates them (distinct tokens) but does NOT (a) NAME the
  split anywhere, (b) model it — the union treats all five as PEERS and even
  `TRIGGER_META` records only `target` (workspace_source/run_artifact/input_value),
  not mechanical-vs-judgment, nor (c) ACT on it — the validator binds + closed-
  vocab's all five identically; `guard-scope` skips the trigger `_when` context
  entirely. This flattening is consequential because the risk is ASYMMETRIC: a
  misfired mechanical trigger needs a filesystem discrepancy (≈impossible between
  faithful runs), but a misjudged `_when` trigger needs only interpretive
  disagreement on prose AND fails OPEN — silently dropping an ENTIRE fragment
  (e.g. the EKS compute path) with no error. Same `_fragments` list, identical-
  looking `_trigger: {...}`, identical validation, wildly different blast radius.
  So for `Trigger` the `@resolution` tag needs NO new derivation mechanism (it
  lines up with the token); the value is in NAMING it + letting checks ACT:
  scope-check `_when` triggers like `_when` guards, and WARN if a fragment's ONLY
  trigger is a `_when` (a misjudgment then silently drops the whole unit of
  work). `Trigger` joins `CheckVerb`'s `_assert` and `_when`'s four contexts as a
  third concrete instance of "one type whose variants straddle the
  mechanical/judgment boundary with nothing marking which side each is on."
- **Derive the phase set + check phase-name references** (closed-vocab anchoring
  for the most load-bearing implicit vocabulary). Phase NAMES are referenced as
  bare strings in many positions — `_check_phase_completed: X`, `_requires_phase:
  X`, `_advances_to: X` (plus `_phase` itself, the `on_confirm` cascade prose,
  and the `_init` `.phase-status.json` write) — but the phase SET is never a
  closed declared vocabulary like `ERROR_ACTION_KINDS`/`TRIGGER_KINDS`.
  CORRECTION (verified against phase-chain.ts): `phase-chain` ALREADY derives
  `phaseSet = { phase | kind==="phase" }` and ALREADY checks `_advances_to`
  (vs phaseSet ∪ terminal {complete,done,end}) and `_requires_phase` (vs phaseSet
  ∪ null), PLUS a reachability/orphan WARNING (a non-first phase no one advances
  to). So the derive-and-check pattern EXISTS. The REMAINING gap is narrower than
  first recorded: **`_check_phase_completed`'s argument is NOT checked against
  phaseSet** (phase-chain covers only advances/requires) — a
  `_check_phase_completed: discovr` in a precondition binds + passes, fails only
  at runtime. FIX: extend phase-chain (it already has `phaseSet`) to also resolve
  every `_check_phase_completed` arg ∈ phaseSet. Small, isolated. DERIVE, do NOT
  add a `phases:` manifest (a second source of truth that drifts from the actual
  `_phase` declarations — the `_on_error` duplication mistake). The pattern is
  the same as `fragment-ref.ts` (collect `_fragment` decls → check `_fragments[]`
  refs) and REF_RESOLVE (paths vs disk).
  STILL-UNBUILT cross-phase chain-integrity (phase-chain does membership +
  reachability, NOT these): (a) advances/requires MUTUAL consistency + acyclicity
  — PROMOTED to its own item below; (b) the parked `on_confirm` cascade ==
  ⋃ downstream `_produces`; (c) `_init`-iff-first-phase (`_init` present ⇔
  `requiresPhase===null` — neither binder nor any check enforces). CAVEAT (all of
  the above): rests on the `phases/`-only discovery scope — same assumption every
  cross-unit check already makes.
  WHEN A MANIFEST WOULD BE RIGHT INSTEAD (not now): if phases became a reusable
  LIBRARY composed into different migrations (set primary, files are members)
  rather than six files in one linear chain (files primary, set is their union).
- **Phase-chain MUTUAL-CONSISTENCY check** (`_advances_to` ⇔ `_requires_phase`
  biconditional) — HIGH value, distinct from what phase-chain does today.
  phase-chain currently checks each pointer for MEMBERSHIP (names a real phase)
  and REACHABILITY (orphan warning), but NEVER checks the two pointers AGREE WITH
  EACH OTHER. The chain is a set of bidirectional edges: discover
  `_advances_to: clarify` and clarify `_requires_phase: discover` are the forward
  and backward halves of ONE edge and must be mutually consistent. INVARIANT: for
  every phase A, `A._advances_to == B` ⇔ `B._requires_phase == A`. Broken cases
  that PASS today: (i) forward link with no matching back-link (discover→clarify
  but clarify requires design); (ii) asymmetric skip (discover→design while
  clarify still requires discover); (iii) back-link with no forward link. WHY IT
  MATTERS (runtime lifecycle bug, not cosmetic): `_requires_phase` is a runtime
  GATE (clarify confirms phases.discover==completed) and `_advances_to` writes
  `current_phase` — an inconsistent edge yields a phase that can never satisfy its
  own precondition, or a handoff pointing at a phase that rejects it; it also
  corrupts the `on_confirm` cascade's transitive-downstream walk. FIX: two loops
  in phase-chain (it already has every phase's advancesTo + requiresPhase) — each
  forward edge has a matching back edge, each back edge a matching forward edge;
  new code e.g. `CHAIN_CONSISTENCY`. BONUS: a mutually-consistent chain with
  exactly one head (`_requires_phase: null`) and one terminal
  (`_advances_to: complete`) IS a single acyclic linear list — so this check +
  a one-head/one-terminal check together give ACYCLICITY nearly for free
  (subsumes the old separate acyclicity item).
- **Missing-`_on_failure`-on-non-`_assert` warning** (unbuilt, documented in
  dsl-types.md Type 4 `Condition`). A `Condition` (one pre/postcondition item) is
  `CheckVerb` + optional `ErrorAction`. Only `_assert` has a DOCUMENTED default
  action when `_on_failure` is omitted (emit `GATE_FAIL | reason=invalid`, halt).
  For the other six verbs, omitting `_on_failure` is allowed by the binder but
  the failure action is underspecified — in practice the LLM halts a failed
  precondition, but the grammar never PINS that for non-`_assert` verbs the way
  it does for `_assert`. dsl-types.md specifies a WARN ("non-`_assert` verb with
  no `_on_failure` → warn; no documented default") but no check is wired. FIX: an
  intra-unit check over each unit's pre/postconditions: `verb.kind !== "_assert"
  && onFailure === undefined` → WARN. Low-consequence (most real conditions omit
  `_on_failure` and the LLM halts anyway), but it is a clean isolated
  documented-but-unbuilt item — same class as the other "validation power this
  unlocks" notes. RELATED (already implied by the duplicate-`_assert` item):
  postcondition PLACEMENT rules (fragment checks its own writes / assembler
  checks final state / phase checks cross-cutting, per unit-taxonomy-spec) are
  CONVENTIONS not checks — `Condition` is unit-agnostic (its `context` tag is
  only pre-vs-post, NOT which-unit-kind), so a cross-cutting assertion sitting in
  a fragment's postconditions goes undetected.
- **`Guarded` minor items** (uniformity + one unbuilt check, from the `Guarded`
  / `GuardedRole` deep-dive). Two things:
  (a) **Path-convention check is UNBUILT though `role` was added to enable it.**
  `GuardedRole` (`knowledge`|`template`) is documented as driving "path +
  semantic checks," and it IS read in `ref-resolve.ts` for orphan-sweep scoping
  (`if (g.role === "knowledge") referencedKnowledge.add(...)`) and to gate
  `JSON_INVALID` to knowledge files only (templates aren't JSON) — both real.
  BUT the THIRD advertised use, PATH CONVENTIONS, has NO check: nothing verifies
  a `knowledge` file lives under `knowledge/<phase>/` or a `template` under
  `templates/<phase>/`. Clean isolated unbuilt check, exactly what `role` was
  supposedly added to enable. FIX: in ref-resolve (it already has role + path),
  assert the path prefix matches the role.
  (b) **`file` vs `_file` bare-vs-underscored inconsistency** — `Guarded` uses a
  BARE `file:` key whose VALUE is fully structural (REF_RESOLVE'd, orphan-swept),
  while `FragmentRef`/`AssemblerRef` use `_file:` for the analogous thing. Same
  bare-vs-underscored wart as `_re_entry_guard`'s sub-keys — a bare key that is
  actually structural muddies the "`_`-keys are structural, bare keys are author
  content" rule. Fold into the same uniformity pass: candidate rename `file` →
  `_file` for consistency across all file-ref sub-keys.

## Decisions / anticipated review questions

Things that WILL come up in PR review (reviewers reach for them independently);
recorded so they don't get re-litigated each time.

- **Q: Why not pull the structural contract into a sibling `.meta` file**
  **(`foo.md` + `foo.meta.md`, like `foo.js`/`foo.test.js`)?** A teammate
  proposed exactly this in response to the rollout proposal; expect it again.
  ANSWER: we DO separate the part that benefits — the lookup DATA (pricing,
  sizing tables) comes out of prose into its own files (that's Rung 1). But the
  STRUCTURAL contract (the closed `_`-vocabulary: preconditions, produces,
  fragments, meta fences) is DELIBERATELY co-located with the prose (FORM-2b:
  frontmatter = contract, body = procedure). Splitting it into a sibling file
  REINTRODUCES DRIFT — prose and contract silently disagreeing — which is the
  exact failure mode the DSL exists to prevent. Co-location means they're
  reviewed together and the `[_uses:]` marker + the validator tether prose refs
  to the contract so they can't diverge. The `foo.test.js` analogy actually
  SUPPORTS this: a test file is separate but MECHANICALLY TETHERED to its source
  and CI runs them together — "separate file kept in sync by a checker" is
  precisely the knowledge-JSON + ref-resolve/xtable/subset model, NOT a reason to
  split the contract. The "runtime noise" cost of co-located frontmatter is real
  but small (the LLM reads past it trivially); the drift cost of splitting is the
  thing we're eliminating.
- **Q: Can we auto-verify the metadata with a code-based tool?** Same teammate
  asked for "a unified flow to turn the metadata into an executable validation
  script." ANSWER: already built — `scripts/dsl-validator/` runs in CI via
  `mise run lint:dsl`. It validates STRUCTURE + DATA INTEGRITY (closed vocab,
  refs resolve, cross-table coverage, orphan/JSON-validity), NOT migration
  output or prose judgment (that's the separate cold-run reproducibility
  discipline — calibrate expectations). The data-integrity slice running on the
  Rung-1 JSON IS Rung 2.
- **Signal:** the teammate above, seeing only the Slack proposal, independently
  asked for (1) extract data into separate files and (2) a code tool to
  auto-verify it — i.e. Rungs 1 and 2. The data-first ordering is intuitive to
  the team; the early rungs will land with a receptive reviewer.

## Incremental rollout plan (replace prose heroku-to-aws with the DSL)

Status: PLAN agreed 2026-06-30. The DSL skill exists today as a THIRD, parallel
skill (`skills/heroku-to-aws-dsl/`) alongside the incumbent prose
`skills/heroku-to-aws/` (on `origin/main`). A big-bang swap is too much for the
team to consume. This plan converges the two until the prose skill can be deleted.

**Goal / audience / channel.** END GOAL: REPLACE prose `heroku-to-aws` with the
DSL (not coexist). AUDIENCE: own team — devs AND product owners — as PR
REVIEWERS. CHANNEL: PRs into `awslabs/startups` (so each PR must self-justify to
external maintainers too). "Value on its own" therefore = each PR is
independently mergeable AND legible to a PO without reading TypeScript.

**Two load-bearing principles (what makes this incremental, not big-bang):**

1. **Data-first.** Rungs 1-2 land on the PROSE skill BEFORE any DSL is
   introduced. They extract knowledge + add a data-linter — pure prose-skill
   improvement, PO-legible, and they build the SHARED data foundation both skills
   then use. The DSL paradigm doesn't reach reviewers until Rung 3.
2. **Terminal-first conversion order.** When converting phases (Rungs 4-8),
   convert BACK-TO-FRONT: feedback first, discover LAST. Each conversion is then
   a leaf (nothing downstream consumes its output as DSL yet), so every
   phase-conversion PR is independently safe + mergeable. Discover-first (the
   intuitive order) is the trap — everything depends on it immediately.

**The rung ladder (each rung = a PR or small cluster; each independently valuable):**

- **Rung 0 — docs/ADR only.** Ship `dsl-language-guide.md` + the type-graph +
  a short "why we're moving heroku-to-aws to a DSL" ADR. No code change. Team
  approves the DIRECTION once, cheaply. (Guide + graph already committed on the
  DSL branch; the ADR + repointing them into a main-based PR is the actual Rung-0
  work.)
- **Rung 1 — extract knowledge into JSON, consumed by the EXISTING prose skill.**
  NO DSL introduced. Decouples the prose skill's lookup data into JSON it
  references; that JSON becomes the SHARED source of truth with the DSL skill.
  Decomposed (it is itself a ladder — see below).
- **Rung 2 — validator's DATA checks as a knowledge-integrity linter in CI.**
  XTABLE (cross-table coverage), ref-resolve, orphan-knowledge, JSON-validity —
  run against the Rung-1 JSON. NOT the grammar checks yet. Catches the RDS-pricing
  -gap class at build. PO value: "we can't ship a migration with a missing
  price." Needs a check first: confirm these run reading JSON directly without
  binding full DSL units (they mostly do — verify).
- **Rung 3 — first DSL phase: feedback (terminal), as explicitly transitional.**
  Ship INTERPRETER + just the grammar feedback needs. Smallest blast radius
  (terminal = no downstream consumer). First concrete look at the new shape.
- **Rungs 4-8 — convert remaining phases terminal→initial:** generate →
  estimate → design → clarify → discover, one PR each. Grammar accretes as
  each phase needs it; validator's structural checks come online per-phase.
- **Rung 9 — retire prose skill + repoint plugin.** Delete `heroku-to-aws`,
  rename `heroku-to-aws-dsl` → `heroku-to-aws`, repoint the plugin manifest.
  This is the rung that makes it a REPLACE, not "we now have two skills."

**Rung 1 decomposition (the immediate next work).** Two KINDS of knowledge in
the prose skill, two sub-problems:

- **Kind A — already standalone reference files** (LOW risk): the 6
  `references/design-refs/*.md` tables (dyno-type, postgres-plan, redis-plan,
  kafka-plan, fast-path, eks-mapping) + `references/shared/pricing-cache.md`.
  These are ALREADY decoupled markdown tables the prose skill looks up by file;
  converting is a FORMAT change (MD table → JSON) + repoint the reference. The
  DSL skill ALREADY has the JSON equivalents (`knowledge/design/*.json`,
  `knowledge/estimate/aws-pricing.json`) — so 1a brings that data into the prose
  skill and the two skills then share ONE source of truth.

  **DATA DIFF DONE (2026-06-30) — verdict SPLIT; see
  `.agents/scratchpad/rung1a-data-diff.md` for the full 7-pair record.** 6 of 7
  pairs are clean mechanical MD→JSON (table values identical); the PRICING pair
  is a RECONCILIATION carrying material rate ADDITIONS (RDS-gap m6g/r6g/x2g
  classes, a net-new MSK section, EKS node rates, fast-path flat baselines — all
  `_note`/`_basis`-flagged). Two pairs (postgres, redis) also pin an interpretation
  the prose left ambiguous (`_rds_proxy` source; redis `_engine_version`) with NO
  table-value change. The EKS pair straddles Kind-A (19 pod rows in
  `eks-mapping-table.md`) and Kind-B (cluster constants + node-sizing formula live
  in `design-eks.md` PHASE PROSE, not the table file).

  **AGREED PLAN (2026-06-30), revising the original "1a = 7 tables, ONE PR":**

  **REPOINT SHAPE (Option A, agreed 2026-06-30):** ONE copy of the data, in JSON;
  the `.md` keeps its PROSE and POINTS at the JSON. Concretely, each
  `references/design-refs/<x>-table.md` keeps its Description / Interpretation
  Notes / Error Handling prose but its `## Lookup Table` section's markdown table
  is REPLACED by a pointer line to the JSON (the rows live ONLY in JSON — NOT
  duplicated in the `.md`). The `.md` stays the load target, so design.md/SKILL.md
  reference lines are UNCHANGED (no Kind-B procedure-prose surgery). One-hop
  indirection (LLM loads the `.md`, follows the pointer to the `.json`) is
  accepted over either (B) deleting the `.md` + moving notes prose into procedure
  (Kind-B risk, deferred to a later rung) or (C) keeping the table in BOTH
  (duplication — the exact drift Rung 1 exists to kill).
  **JSON PATH:** prose-skill JSON lives at `heroku-to-aws/knowledge/design/*.json`
  — MIRRORS the DSL skill's layout so Rung 9 (rename dsl→prose) is a clean rename,
  not rename+file-moves. New top-level `knowledge/` dir in the prose skill; pointer
  from a design-ref `.md` is `../../knowledge/design/<x>.json`.

  - **Rung 1a (mechanical) — DONE + MERGED (PR #87, `origin/main` `cec1467`).** The 5 clean standalone tables → JSON + repoint refs:
    dyno-type, postgres, redis, kafka, fast-path. Pure "same numbers, now JSON."
    Call out the two pinned-interpretation notes (postgres `_rds_proxy`, redis
    `_engine_version`) in the PR description so a reviewer signs off on the
    RESOLUTION, not just the format. No row values change.
  - **Rung 1a-pricing (SEPARATE PR) — DONE + MERGED (PR #88, `origin/main`
    `a69a01d`).** Pricing rates now in `skills/shared/pricing/aws-infra-pricing.json`
    (= the DSL `aws-pricing.json` content, de-DSL'd) at the NEUTRAL location;
    estimate.md Step 0a + cost-formula table + EKS section + CloudWatch block
    repointed to JSON keys (inline rates stripped); heroku `pricing-cache.md`
    symlink removed; SKILL.md + shared/README.md repointed. Cold-validated against
    large-terraform (per-service costs matched ground truth EXACTLY); full mise
    build green. Caught + fixed a leftover inline `$73` EKS control-plane literal.
    TRACKED FOLLOW-UP (do soon, don't let it become permanent): migrate
    gcp-to-aws's estimate to read the SAME shared file + retire its
    `pricing-cache.md` infra sections — closes the temporary two-copy window.
    DESIGN (as built): Pricing was NOT
    a clean mechanical move like the 5 tables — it is Kind-A (a shared cache file)
    + Kind-B (rates HARDCODED INLINE in `estimate.md`) + reviewable additions.
    Audit findings:
    * THREE pricing locations today: (1) `references/shared/pricing-cache.md` — a
      SYMLINK to `gcp-to-aws/.../pricing-cache.md`, the canonical AWS-rate source
      SHARED with gcp (one of SIX heroku→gcp shared symlinks); (2)
      `references/shared/heroku-pricing-cache.md` — a REAL file, SOURCE-side Heroku
      plan prices (for `heroku_monthly_estimated`), NOT AWS rates — OUT OF SCOPE;
      (3) rates HARDCODED INLINE in `estimate.md` (cost-formula table lines
      ~122-140, EKS node-rate table ~159-163, CloudWatch block ~226-229).
    * DRIFT ALREADY REAL: the EKS m6i/r6i node rates exist ONLY inline in
      estimate.md (+ the DSL JSON); the shared cache has NO m6i/r6i (only m5.*).
      So the procedure's numbers are already partly independent of the cache it
      claims to read. MSK / Amazon MQ / OpenSearch are also ABSENT from the cache.
    * OVERLAP AUDIT (gcp vs heroku): big shared INFRA core (Fargate, RDS, Aurora,
      EC2, EKS, ElastiCache, S3, ALB, NAT, Route53, CloudFront, Secrets,
      CloudWatch, X-Ray) used by BOTH; heroku-only = MSK/MQ/OpenSearch; gcp-only =
      the entire Bedrock AI-model table + Lambda/DynamoDB/Redshift/Athena/SageMaker
      + Security Baseline (~60% of the cache is gcp-only AI).
    AGREED DESIGN:
    * SHAPE: one SHARED INFRA JSON = the infra intersection + heroku's
      MSK/MQ/OpenSearch (infra; gcp just won't read those keys). AI-models/Lambda/
      DynamoDB/Redshift/Athena/SageMaker/Security STAY in gcp's markdown cache.
    * LOCATION: NEW NEUTRAL `skills/shared/pricing/aws-infra-pricing.json` (neither
      skill owns it). Ships because the plugin packages ALL of `skills/`
      (codex plugin.json `"skills": "./skills/"`). CONSEQUENCE ACCEPTED: diverges
      from the 6 existing heroku→gcp symlinks — a future-consistency item (migrate
      the other 5 to neutral later), NOT this PR.
    * GAP STRATEGY: heroku migrates NOW, gcp LATER; ACCEPT short-lived two-copy
      drift (markdown cache keeps infra rates for gcp until it migrates). TRACKED
      FOLLOW-UP so "migrate gcp soon" doesn't become "never" (the failure mode of
      this choice).
    * THIS PR TOUCHES (heroku): (a) add the shared JSON; (b) remove heroku's
      `pricing-cache.md` symlink; (c) repoint `estimate.md` Step 0a AND STRIP the
      inline rates from the cost-formula table / EKS node table / CloudWatch block,
      pointing them at the JSON (Kind-B prose surgery — the hard part);
      `heroku-pricing-cache.md` UNTOUCHED (out of scope).
    * REVIEWABLE ADDITIONS ("Data changes (not format)" section): m6i/r6i EKS node
      rates, MSK, MQ, OpenSearch, fast-path `monthly_baseline_est` — present in the
      JSON, absent/inline-only in the markdown today. Same two-audiences logic:
      pricing review = "are these NEW numbers right?" not "same numbers?".
  - **Rung 1b-eks — DONE + MERGED (PR #89, `origin/main` `a390ae4`).** Built per the
    drift audit below + the agreed split (rows + cluster constants + node-rank →
    `knowledge/design/eks-pod-sizing.json`; sizing ALGORITHM stays prose). All 3
    decisions applied: (1) `kubernetes_version` kept query-live, JSON key named
    `kubernetes_version_fallback` so it can't read as a pin; (2) node-sizing clamp
    `desired_size = max(min_size, ceil(total_pods/4))` bugfix; (3) node-rank
    tie-break pinned in `node_size_rank`. Cold-validated 3 fixtures (small-clamp,
    multi-class tie, ram-only tie) — all matched ground truth EXACTLY; mise build
    green. (Original deferral rationale + drift audit retained below.)
  - **Rung 1b.x (EKS, DEFERRED whole)** = `eks-mapping-table.md` rows +
    `design-eks.md` cluster constants extracted TOGETHER as one coherent unit,
    later in the ladder. Consequence ACCEPTED: the clean Kind-A pod rows wait for a
    PR that also edits phase-procedure prose (Kind-B), so EKS convergence lands
    later + heavier — chosen for coherence (one EKS source of truth, no
    half-migrated file) over speed, consistent with the "don't split knowledge
    across PRs / structure stays co-located" principle.

    **EKS DRIFT AUDIT (2026-06-30, done before drawing the EKS PR).** Read
    `design-eks.md` (prose) end-to-end vs `eks-pod-sizing.json` (DSL). The EKS
    extraction is NOT clean-mechanical — it is 1 mechanical part + 1 Kind-B
    extraction + 3 REVIEWABLE DATA DECISIONS:
    - pod-sizing rows (19): IDENTICAL prose-table vs DSL — mechanical (Kind-A).
    - cluster_name / node-group-type-by-pref / addons list: match — Kind-B
      extraction (constants live in `design-eks.md` prose), no value change.
    - **DECISION 1 — `kubernetes_version` (the big one, INVERSE of redis/postgres
      pins):** prose says "query live via `aws eks describe-addon-versions`, ELSE
      default `1.31`, do NOT hardcode"; DSL PINS `1.31` as a constant ('DSL makes
      no AWS calls'). For the PROSE skill, KEEP the query-live-with-`1.31`-fallback
      behavior — do NOT adopt the DSL's static pin (that would REGRESS the
      incumbent, which is not constrained to no-AWS-calls). Extract the FALLBACK
      (`1.31`) + the query INSTRUCTION as data; don't collapse to the pin. This is
      the one case where the DSL value must NOT be carried into prose.
    - **DECISION 2 — node-sizing desired_size clamp (DSL fixed a real prose BUG):**
      prose `desired = ceil(total_pods/4)` can yield `desired=1 < min_size=2` when
      `total_pods <= 4`, which AWS REJECTS; DSL has `desired = max(min_size,
      ceil(total_pods/4))`. ADOPT the DSL clamp into prose as a bugfix (flag for
      review).
    - **DECISION 3 — instance-type rank/tie-break:** prose hand-waves "largest
      dyno type present"; DSL pins `_node_size_rank` + a tie rule (m6i.4xlarge over
      r6i.4xlarge unless a ram-type is the only one at that rank). ADOPT the DSL
      rank into prose as a CLARIFICATION (low-risk).
    NET: the EKS PR carries 3 judgment calls (one of which is 'do NOT adopt the
    DSL value'), confirming deferring-it-whole was right — splitting the clean rows
    out would orphan the decisions. The PR needs a "Data decisions" section like
    the pricing PR.

  - **Rung 1b-estimate (estimate-defaults extraction) — PR #90 OPEN 2026-06-30
    (awaiting review).** SCOPE NARROWED from the original audit during the build:
    only the 2 genuinely heroku-estimate-specific tables were extracted to
    `knowledge/estimate/estimate-defaults.json` — `log_volume_gb_per_service` +
    `optimization_savings_ranges`. Cold-validated (32 GB/mo log volume + correct
    optimization gating incl. s3 excluded for S3-less design); mise build green.
    KEY INVESTIGATION FINDING: the complexity-tier bands + timeline weeks are
    ALREADY in the SHARED `references/shared/migration-complexity.md` (heroku
    symlinks it, gcp-owned), and estimate.md RESTATES a DRIFTED subset inline
    (timeline Small `2-6` vs the shared file's `2-4`/`3-6`). So those were NOT
    extracted (pulling them into a heroku file = a 3rd divergent copy). Cost-tier
    multipliers + metric/alarm heuristics stay prose (algorithm). The optimization
    output skeletons stay (output templates); JSON keys named
    `target_services`/`timing` to match them.
    NEW TRACKED FOLLOW-UP — **complexity-drift fix:** make estimate.md DEFER to the
    shared `migration-complexity.md` (it already says "Load" it) and DELETE its
    drifted inline bands/timeline restatement. Heroku-only prose bug-fix, its own
    small PR. Separately, migration-complexity.md itself is a gcp-owned shared
    markdown (like pricing-cache was) — a FUTURE shared-file convergence thread if
    we ever JSON-ify it, but PREMATURE now (the DSL kept complexity as prose; no
    convergence target; gcp blast radius). Do NOT move/JSON-ify it yet.
  - **Rung 1b-estimate (estimate-defaults extraction) — IDENTIFIED 2026-06-30,
    deferred to its own PR.** While reviewing PR #88 we asked "is the formula
    knowledge?" → settled NO (algorithm lives in prose; the LLM executes it; a
    formula-as-JSON-string would force a pointless parse step). But "are the OTHER
    estimate.md tables knowledge?" → mostly YES. Audit (vs the DSL
    `estimate-defaults.json`, which already extracted them): estimate.md has TWO
    knowledge bodies — (a) AWS RATES (PR #88, done) and (b) ESTIMATE DEFAULTS =
    tunable org assumptions. Tables that are DATA → a prose-skill
    `estimate-defaults.json`: cost-tier multipliers (1.5/1.0/0.7),
    log-volume-per-service constants (Fargate 3GB / RDS 1GB / ALB 2GB / NAT 1GB /
    ElastiCache 0.5GB / MSK 2GB), custom-metrics/alarms heuristics, complexity-tier
    bands + timeline weeks, optimization savings catalog (20-66% etc.),
    has-databases service set. Tables that STAY PROSE (algorithm/decision-logic):
    per-service cost formulas, pricing hierarchy, recommendation-path logic. MCP
    recipe table stays (MCP config). WHY ITS OWN PR, not folded into #88: different
    knowledge category (org-tunable, heroku-specific — NOT shared with gcp, so NOT
    in `skills/shared/`; the DSL keeps rates and defaults in two files for this
    reason), more Kind-B prose surgery on the complexity/optimization sections, and
    #88 is already validated + open. Sibling of the EKS Kind-B PR.
- **Kind B — interleaved in phase prose** (HIGHER risk, one phase per PR):
  `design-defaults`, `estimate-defaults`, `clarify-questions`,
  `generate-routing`, `feedback-config` were extracted DURING the DSL work and
  have no standalone prose home — they live inside `design.md`/`estimate.md`/etc.
  Decoupling = surgically removing inlined constants from procedure prose +
  pointing at JSON. Rungs 1b.1-1b.5, one phase each.

**OPEN QUESTION gating Rung 1a (run FIRST, read-only): the data diff.** Are the
DSL JSON files faithful representations of the prose MD tables, or did they
DIVERGE during DSL work (likely — the DSL work fixed the RDS pricing gap, added
`db.m6g.*` classes, pinned values, added EKS tables)? If clean → 1a is a
mechanical format conversion. If diverged → 1a is format conversion + a
REVIEWABLE set of data corrections (POs approve the data changes). Diff one pair
first (`dyno-type-table.md` vs `dyno-fargate-sizing.json`) to learn the shape.

**Branch / worktree / git mechanics.**

- Rung-1 branch: `feat/heroku-knowledge-extract-tables`, based on CLEAN
  `origin/main` (NOT this DSL branch — branching off the DSL branch would carry
  all 16 DSL commits into a supposed-to-be-DSL-free PR).
- Use a separate WORKTREE at `../startups-rung1` so the DSL branch stays intact +
  readable (Rung 1 brings data FROM the DSL JSON), DSL-contamination is
  impossible (DSL skill isn't on disk in a main-based tree), and there's no
  checkout churn between two very different roots.
  `git worktree add ../startups-rung1 -b feat/heroku-knowledge-extract-tables origin/main`
- Each rung = its OWN branch off the latest merged `origin/main` → PR → merge →
  repeat (linear, not stacked — simpler for a learning team).
- Push to `fork` (`icarthick/startups`); PR fork → upstream `awslabs/startups`.
  NEVER `git push origin <branch>`.

## How to resume

0. **ACTIVE FRONT: Rung 1 of the incremental rollout (see the section above).**
   - **GRAMMAR INTRODUCTION STARTED — PR #91 OPEN (phase frontmatter + minimal
     INTERPRETER).** First time the phase/fragment/assembler vocabulary + an
     interpreter contract touch the PROSE skill on main. Scope: discover.md gains
     phase frontmatter (`_phase`/`_title`/`_init`/`_input`/`_fragments`[terraform
     `_always`, billing `_glob`]/`_assemble`/`_produces`/`_advances_to`); NEW
     `INTERPRETER.md` (prose-skill-local, de-DSL'd) defines how to read the
     frontmatter + the `_trigger` forms + a full `_init` definition; NEW
     `discover-assemble.md` (Step 3 moved verbatim = the assembler unit); SKILL.md
     gains a short pointer to INTERPRETER.md. `_init` is the FIRST LOAD-BEARING
     key — its migration-state-init procedure lives ONLY in INTERPRETER.md (Step 0
     prose REMOVED), one source of truth. discover-terraform/billing fragments
     UNCHANGED. Cold-validated TWICE (fragment routing: terraform fires, billing
     skips on empty glob, assembler resolves; _init: agent initializes state from
     INTERPRETER alone, before fragments, zero divergence). mise build green.
     This is Rung-3-flavored but SCOPED to one cross-cutting capability (`_init`)
     on the only phase that has it (discover) — NOT a full phase conversion, so
     the terminal-first ordering doesn't bind. NEXT load-bearing step (full
     phase->interpreter-driven conversion) should still go TERMINAL-FIRST
     (feedback), after #91 establishes the vocabulary.
     **VALIDATION FOLDED IN (Rung-2-flavored):** #91 also adds
     `scripts/validate-frontmatter.mjs` (zero-dep Node 24) wired into `mise run
     lint`/`build` — checks `_file` ref-resolve, closed `_`-vocab (typo catch),
     fragment `_id`↔phase-ref match, `_of_phase` back-ref, `_trigger` well-formed,
     `_advances_to`/`_requires_phase` name real phases, single-creator ownership.
     Proven to CATCH ref-break/typo/id-mismatch (build fails), clean passes. AND
     the two fragment files (discover-terraform/billing) gained minimal
     `_fragment`/`_of_phase`/`_contributes` frontmatter so the validator has 4
     real units + cross-refs to check (grows the footprint so validation earns
     its keep). Fragments CONTRIBUTE sections to the one inventory (assembler is
     sole creator) — honest `_contributes`, not invented per-fragment files.
     Bespoke validator chosen over porting the DSL TS validator (no TS toolchain
     into prose-skill CI; ~140 lines). `mise.toml` change flagged for
     @awslabs/startups-admins in the PR. This means the classic Rung 2 (port the
     DSL data-integrity checks) is PARTIALLY satisfied for frontmatter; the
     xtable/knowledge-JSON checks remain a later item if wanted.
     **UPGRADED to a TYPED validator (2026-06-30).** The regex `.mjs` was replaced
     by a TypeScript validator at the PLUGIN ROOT (`tools/frontmatter-validator/`
     — types.ts/parse.ts/check.ts/validate.ts), type-checked by `tsc --noEmit`
     (added `npm:typescript`), with a `node:test` suite at
     `tests/tools/frontmatter-validator.test.ts` (ephemeral good/bad fixtures;
     never commits a bad edit). KEY ARCHITECTURE DECISION: the validator is
     SKILL-AGNOSTIC and lives at the PLUGIN ROOT, not inside the skill — it is
     shared infra run AGAINST skills (finds phase/fragment/assembler files by the
     `references/phases/<name>/` convention), must NOT ship in the packaged skill
     tree, and DERIVES the valid phase set from declared frontmatter (no hardcoded
     heroku phase list) so it covers gcp-to-aws unchanged once gcp gets
     frontmatter. Matches the repo's existing plugin-root `tests/` convention
     (tests are NOT inside skills). Mirrors the DSL validator's zero-dep TS recipe
     (Node 24 type-stripping + tsc + node-shims.d.ts) but is the lean shared
     structural checker, distinct from the DSL skill's in-skill grammar validator.
     Motivation: a CI-demonstrable value story for the team — green build proves
     the frontmatter is valid; the test suite (bad fixtures) proves CI WOULD catch
     a bad edit, without ever committing one.
   - **Rung 1a-mechanical: DONE + MERGED (2026-06-30, PR #87 = `origin/main`
     `cec1467`).** The 5 clean tables (dyno, postgres, redis, kafka, fast-path)
     are now JSON under `heroku-to-aws/knowledge/design/*.json` with the prose
     `.md` files repointing at them (Option A). Cold-agent validated against the
     large-terraform sample (all design mappings reproduced exactly); full
     `mise run build` green. The `feat/heroku-knowledge-extract-tables` branch +
     `../startups-rung1` worktree were deleted post-merge.
   - **NEXT: Rung 1a-pricing (its own PR).** Adopt `aws-pricing.json` into the
     prose skill (`knowledge/estimate/`), repoint heroku estimate refs ONLY.
     `pricing-cache.md` is a SYMLINK shared with gcp-to-aws and STAYS. Carries a
     "Data changes (not format)" table for the rate ADDITIONS (RDS-gap m6g/r6g/x2g,
     net-new MSK section, EKS node rates, fast-path baselines) — see the data-diff
     scratchpad + the Rung-1 decomposition above. New branch off the UPDATED
     `origin/main` (`cec1467`+), separate worktree, push to `fork`, PR → upstream.
   - **THEN: Rung 1b-eks (its own PR).** pod rows (mechanical) + `design-eks.md`
     cluster constants (Kind-B) + the 3 reviewable decisions from the EKS drift
     audit (keep query-live `kubernetes_version` — do NOT adopt the DSL pin; adopt
     the node-sizing `max(min_size,…)` clamp as a bugfix; adopt the `_node_size_rank`
     tie-break as a clarification). Needs a "Data decisions" section.
   SCOPE GUARDRAIL: Rung 1 extracts only the knowledge DATA (lookup tables) into
   separate files. Keeping the STRUCTURAL contract co-located with prose is a
   SETTLED decision (drift prevention — see "Decisions / anticipated review
   questions" above); do NOT pull structure into sibling files even if a reviewer
   suggests it or it seems cleaner.
   MECHANICS NOTE: each rung is its OWN branch off the latest merged `origin/main`
   in a SEPARATE worktree (linear, not stacked). edit/write tools resolve relative
   paths against the MAIN repo CWD — use ABSOLUTE paths when editing in a secondary
   worktree, and verify with `git status` IN that worktree.

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

## Tracked follow-ups (discovered during the frontmatter/validator work)

- **The 7 pre-existing plugin tests are DORMANT** (`tests/property/heroku/*.test.js`
  + `tests/integration/heroku/*.test.js`). They `import fc from 'fast-check'` but
  fast-check is NOT a declared/installed dependency anywhere — running one fails
  immediately (exit 1). So they don't run today, aren't wired into CI, and gate
  nothing. Consequence: PR #91's frontmatter-validator test is the FIRST
  actually-running, CI-gating test in the plugin. FOLLOW-UP (own PR, not #91):
  revive them — declare/install fast-check, get its types resolving under the
  zero-@types tsc setup, convert `.js`->`.ts` for a uniform typed suite, wire into
  build. ~2,765 lines; unrelated to frontmatter; do NOT bundle.
- **DECISION (tests language):** the validator test is TypeScript (`.ts`,
  tsc-checked via the plugin-level `migrate/plugins/migration-to-aws/tsconfig.json`)
  — honoring "TypeScript for tests". It was briefly made `.js` to "match the
  existing suite" then reverted once we found that suite is dormant (matching a
  non-running suite was a weak reason). New tests should be `.ts`.
- **VALIDATOR REACH \u2014 broaden to ALL skills (tracked follow-up).** The frontmatter
  validator (`tools/frontmatter-validator/validate.ts`) is the PRIMARY value: it
  lets authors/reviewers catch structural inconsistencies in a skill's
  phase/fragment/assembler frontmatter at PR/CI time. It is already skill-AGNOSTIC
  (takes a skill-root arg, derives phases, no hardcoded skill), BUT the mise
  `lint:frontmatter` task currently invokes it against ONE skill
  (`skills/heroku-to-aws`) because that's the only skill with frontmatter today.
  WHEN a 2nd skill gets phase frontmatter (e.g. gcp-to-aws), broaden the invocation
  to DISCOVER + check every `skills/*/` that has a frontmatter'd phase (small
  change: loop over skill dirs in validate.ts or the task). Deferred now (YAGNI /
  keep #91 focused); the value is latent until multi-skill. Before broadening,
  verify the `references/phases/<name>/<name>.md` convention holds across skills so
  a scan won't miss/false-positive.
