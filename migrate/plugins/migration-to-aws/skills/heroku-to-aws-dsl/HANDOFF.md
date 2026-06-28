# heroku-to-aws-dsl — Handoff

_Last updated: 2026-06-28. Branch: `feat/heroku-dsl-refactor` (off `origin/main`)._

## What this is

A **third** expression of the heroku-to-aws migration skill, alongside the two
that exist in the repo:

- `skills/heroku-to-aws/` (upstream **pure markdown**, on `main`)
- the **MCP engine** refactor (`feat/heroku-mcp-refactor`, deterministic logic in
  Python tools + JSON)
- **this**: a declarative **phase DSL the LLM interprets at runtime** — NO engine,
  NO server. CI validates the DSL structure statically; the LLM enforces
  pre/postconditions at runtime by reading them.

Core principle: **structure is checkable (DSL), judgment is the LLM's (prose).**
A DSL makes STRUCTURE checkable but does NOT make ARITHMETIC deterministic — the
clamp/sizing/cost-math leaves are the same "must this be deterministic?" fork,
now isolated to specific phases (design, estimate).

## of 6 phases done

| Phase        | State                                                                                                                                                                                                                                                                                                                                                                                                      |
| ------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **discover** | ✅ DONE — authored, refactored to the unit taxonomy, cold-LLM validated (incl. billing + re-entry)                                                                                                                                                                                                                                                                                                         |
| **clarify**  | ✅ DONE — ported as 1 fragment (interview) + no-op/validator assembler; cold-LLM validated; new `preferences.schema.json`. See `test-output/clarify-verdict.md`.                                                                                                                                                                                                                                           |
| **design**   | ✅ DONE — ported as 1 mapping fragment + validator assembler (route gates) + 5 `knowledge/design/*.json` tables + `aws-design.schema.json`; EKS branch is a loud-halt stub (not authored). Cold-LLM validated on TWO fixtures incl. a hard one (clamp + re-derive trap + distinct RDS/Aurora cols + peering + Fir). Arithmetic-probe + verdict in `test-output/`. The DSL thesis HOLDS for the math phase. |
| estimate     | ⏳ not started. Cost arithmetic + aws-pricing knowledge. Builds on design.                                                                                                                                                                                                                                                                                                                                 |
| generate     | ⏳ not started. Multi-fragment + multi-artifact (terraform/ + guide + scripts) — the real stress test of the assembler's multi-artifact case.                                                                                                                                                                                                                                                              |
| feedback     | ⏳ not started.                                                                                                                                                                                                                                                                                                                                                                                            |

## The DSL architecture (settled this session)

### Three unit kinds (see `docs/unit-taxonomy-spec.md` for the full spec)

- **Phase** — lifecycle + composition. Frontmatter: `_phase`, `_requires_phase`,
  `_scope`, `_input`, `_init` (first phase only), `_re_entry_guard`,
  `_preconditions`, `_fragments` (ordered `{_id,_trigger,_file}` list),
  `_assemble` (`{_file}`, mandatory), `_postconditions` (cross-cutting only),
  `_produces`, `_advances_to`, `_forbids_files`, `_on_error`.
- **Fragment** — ONE responsibility → 1..N artifacts WRITTEN DIRECTLY to disk.
  Own frontmatter: `_fragment`, `_of_phase`, `_scope`, `_produces`,
  `_postconditions` (on its own files), `_on_error`. Never reads another
  fragment's output (NO inter-fragment deps). Multi-artifact only if same
  source/reason-to-change.
- **Assembler** — exactly one per phase, terminal. Combines/enriches. Frontmatter:
  `_assemble`, `_of_phase`, `_scope`, `_reads`, `_mutates` (in-place edits),
  `_produces` (new files), `_postconditions` (on mutated+created files). May be
  no-op/promote; still owns the artifact-level contract.

### Key rules

- Creator/mutator: each artifact has ONE creator (fragment or assembler) + 0..N
  mutators (assembler only). Last writer owns final postconditions.
- `_re_entry_guard` is a TOP-LEVEL phase key (NOT in `_postconditions`),
  evaluated PRE-STEPS. On confirm → cascade reset of downstream phases.
- Closed `_`-vocabulary applies inside ALL unit files (typo'd key fails loudly).
- Trigger lives in the PHASE's `_fragments` list, not the fragment.
- **Knowledge/contract/procedure separation** (taxonomy spec): tunable constants
  → `knowledge/` (per-phase `*-defaults.json` sheet); output shape → schema;
  algorithm → step prose. Don't inline a constant a step references. Applied to
  design (`design-defaults.json`) AND clarify, where it went furthest: the whole
  question set is `knowledge/clarify/clarify-questions.json` and the interview MD
  is a generic data-driven driver. Both re-cold-tested behavior-preserving.
- **Unit-file grammar** (INTERPRETER “Unit file regions”): every unit file is
  frontmatter → H1 → exactly one `## Orientation` (non-normative context) →
  `## Step:`* — nothing else. No `## Output`/`## Scope` trailing sections
  (they duplicated `_produces`/`_scope`); no normative rule in H1/Orientation.
  All 11 existing unit files conform; design re-cold-tested behavior-preserving.

## Files

```
INTERPRETER.md                  ← shared interpreter (the DSL vocabulary). Read first.
SKILL.md                        ← entry point
phases/discover.phase.md        ← thin phase: _fragments + _assemble
phases/discover/
  discover-terraform.md         ← fragment: creates heroku-resource-inventory.json
  discover-billing.md           ← fragment: creates billing-profile.json (optional)
   discover-assemble.md          ← assembler: mutates inventory to fold in billing + validate
phases/clarify.phase.md          ← thin phase: 1 fragment + no-op assembler
phases/clarify/
  clarify-interview.md          ← fragment: the adaptive Q&A; creates preferences.json
  clarify-assemble.md           ← assembler: no-op/promote; validates schema + checklist
phases/design.phase.md           ← thin phase: 1 mapping fragment + validator assembler (+ EKS stub)
phases/design/
  design-mapping.md             ← fragment: single-pass map + VPC + Fir; creates aws-design.json
  design-assemble.md            ← assembler: validator; schema + route output gates
  design-eks.md                 ← EKS branch STUB (loud halt; not yet authored)
knowledge/design/               ← 5 lookup tables as DATA (dyno/postgres/redis/kafka/fast-path)
schemas/heroku-resource-inventory.schema.json
schemas/preferences.schema.json
schemas/aws-design.schema.json
fixtures/acme-store/            ← cold-test fixture (tf + Procfile + app.json + billing csv)
fixtures/acme-store-resumed/    ← re-entry test fixture (completed-through-clarify state)
test-output/                    ← verdicts + the taxonomy spec (see below)
```

## Validation done (all cold-LLM, fresh Claude Code, zero repo context)

- `discover-report.md` — base discover executability PASS (Form 2b + billing).
- `reentry-cascade-verdict.md` — re-entry halt + cascade-on-confirm PASS; caught
  the guard-evaluated-too-late bug (fixed: guard hoisted to pre-steps top-level).
- `discover-routes-refactor-verdict.md` — the interim routes refactor.
- `discover-3kind-refactor-verdict.md` — the final taxonomy PASS; cold LLM judged
  separate frontmatters a HELP, the `_reads/_mutates/_produces` triad the
  clarifying core. Caught a stale comment + source-tag (both fixed).
- `discover-upstream-coverage-audit.md` — confirmed nothing dropped vs upstream's
  3 discover files; restored 2 gates (single-active-phase, Procfile-command).
- `clarify-verdict.md` — clarify port PASS; the single-fragment + no-op-validator
  shape executes cleanly. Fixed D1 (Q5b self-contradiction), D2 (Q5b/Q6b
  duplication → canonical Q6b), F2 (`private_space_detected` unreachable), D3
  (timestamp source). Sanctioned validator-assembler reading the phase input in
  INTERPRETER (F1). F3 (db size needs design's knowledge JSON) deferred.
- `design-arithmetic-probe.md` — pre-authoring probe of the design math in
  isolation. Finding: design's "arithmetic" is lookup + 0–100 clamp + tier
  branches; the real threat is RE-DERIVATION, neutralized by demoting source
  figures to labeled provenance. PASS (incl. the 14336→16384 trap, clamp,
  unknown-type reject).
- `design-verdict.md` — design port PASS on TWO fixtures (easy + a hard one
  built after the cold LLM flagged fixture-1 as under-testing). Hard fixture hit
  every trap correctly: clamp 150→100, re-derive trap (16384 on 2 formations),
  case-fold, distinct RDS-vs-Aurora column, rds_proxy from the right field
  despite a colliding provenance value, kafka tier branch, prefix-alias
  fast-path, defer, existing_vpc, Fir detect-only. Fixed 6 findings incl. 3 real
  closed-vocab violations (`_status`, `_halt`, `_eks-compute-mode`); added
  `_when` as a fragment trigger form. **The DSL thesis HOLDS for the math
  phase.**

## Known debt / decisions for next session- `docs/unit-taxonomy-spec.md` is a DESIGN doc misfiled under test-output;

promote it to a real docs location.

- The chain-derived `_re_entry_guard` cascade fallback is unverified until 2+
  phases exist (discover uses an inline `on_confirm` stopgap).
- "Explicit confirmation" for re-entry is undefined (no canonical prompt/token).
- `line_item_csv` billing format is detected but unparsed — INHERITED from
  upstream, NOT a regression; do not invent parse logic (would diverge).
- No CI yet — the DSL's checkability is specified but no validator implemented.
- This work could become its own skill ("authoring-the-heroku-dsl"); not created
  yet (confirm with user first).

## How to resume

1. Read `INTERPRETER.md` (the vocabulary) + `docs/unit-taxonomy-spec.md`.
2. Next phase: **estimate** — the GENUINELY harder arithmetic (chained
   multiply/sum/round cost math, premium/optimized tier derivation, post-loop
   cluster costs + aws-pricing knowledge). Design passing did NOT pre-clear it;
   probe estimate's chained math the same way (isolate, cold-test) BEFORE
   building generate on top. design is done. Also outstanding: author the EKS
   design branch (currently a loud-halt stub) — all-or-nothing port of upstream
   design-eks.md + eks-mapping-table.md, mirror the MCP refactor's EKS approach.
3. Source of truth for what each phase must do: the upstream markdown at
   `skills/heroku-to-aws/references/phases/<phase>/`.
4. Every phase: author → cold-LLM test from a fresh subagent (sandbox blocks
   writes, so it computes + we transcribe/validate) → write a verdict.
