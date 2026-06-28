# Clarify Phase (DSL port) — VERDICT

**Change:** Ported Phase 2 (Clarify) from the upstream pure-markdown skill
(`skills/heroku-to-aws/references/phases/clarify/clarify.md`) into the DSL as the
first **single-linear-job** phase under the unit taxonomy:

- `phases/clarify.phase.md` — thin phase (re-entry guard, preconditions on the
  discover inventory, ONE fragment + one assembler, advances to design).
- `phases/clarify/clarify-interview.md` — the ONE fragment: the LLM-driven
  adaptive interview (fast-path gate, conditional question activation, three
  progressive batches, draft resume, the full question catalog + defaults
  table). CREATES `preferences.json`.
- `phases/clarify/clarify-assemble.md` — the mandatory assembler as a **no-op /
  promote validator**: creates and mutates nothing; READS `preferences.json`
  (and the inventory, to evaluate conditional gates) and owns the artifact-level
  contract (schema + the upstream Validation Checklist / handoff gate).
- `schemas/preferences.schema.json` — new artifact contract (required vs
  conditional-omitted sections, enums, subnet/vpc patterns).

**Why this shape:** clarify is one responsibility (run the interview, write one
artifact), so the taxonomy's "single-job phase = 1 fragment + no-op assembler"
case applies. The point of porting it second was to validate that the taxonomy —
designed against discover's 2-fragment merge — reads cleanly on a degenerate
single-fragment phase, and that a pure-validator assembler earns its mandatory
existence.

## Cold-LLM test: PASS

A fresh Claude (zero repo context) read INTERPRETER.md + SKILL.md, loaded the
clarify phase, and executed it against the real `discover-inventory.actual.json`
(acme-store: 1 app, Postgres + Redis, a Private Space WITHOUT peering, Cedar, no
Kafka, no Fir) with a scripted answer set (interim-cutover, HIPAA, multi-az-ha,
eks-managed, several skips). Results:

- **Phase mechanics correct end-to-end:** `_init` skipped (not first phase),
  re-entry guard a no-op (no `aws-design.json`), all 4 preconditions pass,
  fragment fires (always-trigger), assembler validates, phase advances.
- **Conditional question logic right against the fixture:** active vs
  skipped-not-applicable derived correctly — `Q8` (no Kafka), `Q9/Q9b` (peering
  false), `Q11` (no Fir) all skipped-N/A; Postgres questions active.
- **Fast-path correctly NOT offered** — `has_space` disqualifies it (the LLM
  derived this itself rather than trusting prose).
- **Draft lifecycle correct:** draft written after batch 1 and 2, not after the
  last batch, deleted at the end; phase postcondition confirms deletion.
- **Produced `preferences.json` validates** against the new schema (walked every
  required key + each conditional rule) and **clears all 16 assembler
  postconditions** → `HANDOFF_OK | phase=clarify | artifacts=preferences.json`.
- **Closed-vocabulary holds:** the LLM scanned every `_`-key across the phase,
  fragment, and assembler frontmatter/meta blocks against INTERPRETER.md — all
  defined, no Golden-Rule-4 violation.

## Findings

1. **D1 — Q5b self-contradiction (real defect, FIXED).** The active-questions
   table listed "Q5b Migration urgency | Always" while the catalog entry for Q5b
   was "Migration approach | _(only when has_postgres)_" — two different
   meanings for one id, plus a name drift (urgency vs approach). Inherited
   straight from the upstream markdown, which is itself internally inconsistent
   (there is no real "migration urgency" question — only a fast-path default
   `migration_urgency: routine`). Fixed by removing the phantom Q5b/urgency row.
2. **D2 — Q5b/Q6b duplication (real defect, FIXED).** Upstream lists migration
   approach TWICE (Q5b in the Global batch, Q6b in the Data batch) as the same
   `global.migration_approach` constraint, in different batches, with no
   canonical id — so `sources`/`questions_asked` bookkeeping was ambiguous (the
   LLM had to guess and recorded only "Q5b"). Fixed: migration approach is now
   ONE Postgres-gated question with canonical id **Q6b** in Batch 2; an explicit
   note forbids also asking/recording Q5b. Defaults table + catalog updated to
   match.
3. **F2 — `private_space_detected` was unreachable (real gap, FIXED).** The
   `network` section was populated only from PEERING, but a Private Space can
   exist without peering (as in the fixture). So `private_space_detected` could
   never become `true` despite a space existing. Fixed: write the `network`
   section with `private_space_detected: true` whenever a space exists
   (`has_space`), even with null/empty vpc/subnet fields; omit `network` only
   when no space exists. Schema permits a network section carrying just that
   flag (no required network keys).
4. **D3 — timestamp source undefined (minor, FIXED).** The artifact shape showed
   `metadata.timestamp` with no source. Added "use the current wall-clock time
   (ISO 8601 UTC)" to the assemble step.
5. **F1 — no-op assembler reads the phase INPUT, not just fragment outputs
   (legitimate-but-awkward, RESOLVED at the taxonomy level).** The validator
   assembler reads `heroku-resource-inventory.json` (the phase `_input`) to
   evaluate conditional gates ("database_ha required only if Postgres present").
   The LLM flagged this as stretching "assembler combines fragment outputs."
   Resolved by amending INTERPRETER's `_assemble._reads` doc to explicitly
   sanction a validator/no-op assembler reading the phase's own `_input` for
   trigger-dependent contracts — it is still validate, not discovery.
6. **F3 — `db_size_source` written without `estimated_db_size_gb` (accepted).**
   The Q6c size hint leans on a postgres-plan storage lookup whose backing data
   (`knowledge/design/*.json`) is not ported until the design phase, so the
   numeric size isn't derivable yet and only the `source` tag is emitted. Both
   fields are schema-optional; this is an expected consequence of porting
   clarify before design, not a clarify defect. Revisit when design lands.

## Net

The clarify phase is ported and cold-LLM validated. The single-fragment +
no-op-assembler shape executes cleanly and the separate frontmatters tested as a
net help (the cold LLM: the `_reads`/`_mutates`/`_produces` triad and per-unit
scope/postconditions made the fragment-owns-write-time vs
assembler-owns-artifact-contract split legible; forcing a pure-validator
assembler to exist gives the schema + conditional checklist a clear owner). The
acknowledged cost is modest postcondition overlap between the fragment and the
validator assembler (both assert clarify_mode/target_region/kubernetes/sources)
and the validator reaching back to the phase input — both judged acceptable for
taxonomy uniformity, the latter now explicitly sanctioned in the interpreter.

Three real defects (D1, D2, F2) and one minor (D3) fixed; two seams (F1, F3)
documented as accepted. The taxonomy now holds on both a multi-fragment merge
phase (discover) and a single-fragment validator phase (clarify). Next: design —
the arithmetic checkpoint.

## Addendum (2026-06-28) — data-driven interview engine

Applied the knowledge-separation rule (`docs/unit-taxonomy-spec.md`) to clarify,
which was the most data-heavy phase: the ENTIRE question set — prompts, options,
answer→value maps, triggers, defaults, validations (subnet/VPC regexes), batch
composition, fast-path config — moved out of the interview prose into
`knowledge/clarify/clarify-questions.json`. `clarify-interview.md` is now a
generic DRIVER (algorithm only): derive inventory_facts → evaluate each
question's `trigger` → iterate `batches` → present/interpret per the question's
JSON entry → default → assemble. The Question Catalog + Defaults Table are gone
from the MD (~80% of the file was data). Output SHAPE stays in the schema.

**Regression cold-test (acme-store, re-run):** PASS, behavior-preserving —
identical `preferences.json` in substance (eks-managed, hipaa, multi-az-ha,
interim cutover + exit date + ktlo_warning, Q8/Q9/Q9b/Q11 skipped-N/A, fast-path
not offered). The cold LLM ran the whole interview from the JSON + algorithm
with NOTHING inlined, found no missing question data, no closed-vocab violation,
no unclassifiable region.

Open note (non-blocking): `fast_path.extra_defaults.migration_urgency: routine`
references a field with no question and no `preferences.schema.json` property —
inherited from upstream, reachable ONLY on the fast path (untested by the
full-flow fixture). Either add it to the schema or drop it; needs a dedicated
fast-path cold-test to exercise.
