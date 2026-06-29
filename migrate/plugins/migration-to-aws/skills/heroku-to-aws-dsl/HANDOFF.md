# heroku-to-aws-dsl — Handoff

_Last updated: 2026-06-29. Branch: `feat/heroku-dsl-refactor` (14 commits ahead of
`origin/main`; nothing pushed). `mise run build` green._

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
(producer-emits ∈ consumer-keys — the RDS-gap catcher, regression-verified).

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

## Known debt / decisions for next session

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
