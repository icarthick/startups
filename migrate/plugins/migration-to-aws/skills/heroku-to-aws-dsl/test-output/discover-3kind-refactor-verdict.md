# Discover 3-Kind Refactor (phase / fragment / assembler) — VERDICT

**Change:** discover's body went from `_routes` (peer sub-units, in-memory
contributions) to the agreed **unit taxonomy**: a thin phase composing
**fragments** (terraform, billing) + one **assembler**, each a first-class DSL
unit with its OWN frontmatter. Fragments WRITE artifacts to disk; the assembler
reads/mutates/validates. Spec: `test-output/unit-taxonomy-spec.md`.

**Why (the design thread):** the route-refactor left sub-unit files as anonymous
markdown — not structurally testable, and per-route postconditions piled up in
the phase. The taxonomy fixes both: every unit has frontmatter (closed-vocab +
postconditions checkable inside it), and contracts live where they belong
(fragment owns its write-time checks, assembler owns artifact-final checks).
Walked back "fragments never write files" (a heroku-small assumption) because
gcp discover produces large files (`gcp-resource-inventory.json` +
`gcp-resource-clusters.json`) that must materialize to disk. Settled: a fragment
produces 1..N artifacts from ONE responsibility (reason-to-change guard); no
inter-fragment dependencies; assembler may mutate-in-place and/or create.

## Cold-LLM re-test: PASS — and the separate frontmatters tested as a HELP

A cold LLM executed discover from the 3-kind structure. Results:
- **Unit model understood from the interpreter alone**, mapped to the fixture
  "1:1 with zero surprises."
- **File flow correct:** terraform CREATES the inventory, billing CREATES
  `billing-profile.json`, assembler READS both + MUTATES the inventory. Creator/
  mutator model "crystal clear."
- **Same correct result:** 10 resources, every hard case right (incl. the new
  app-space link rule and the billing dyno_cost-not-dyno_units trap), schema
  valid, `HANDOFF_OK`.
- **Postcondition split validated:** "non-overlapping... write-time correctness
  at the fragment, final-shape/schema at the assembler, existence/cross-cutting
  at the phase."
- **Verdict on the concern that drove this:** "separate frontmatters HELPED...
  let me reason about each unit in isolation... the `_reads`/`_mutates`/
  `_produces` triad is the single most clarifying thing in the design — it told
  me the data flow before I read a line of step prose." → the testability +
  contract-locality concern is resolved.

## Findings

1. **Stale header comment (real defect, FIXED).** The phase's banner still
   described the old `_routes`/in-memory model ("NO intermediate `_`-artifacts")
   — contradicting the now file-writing fragments. The LLM caught it (Golden
   Rule 4 didn't fire because `_routes` wasn't in frontmatter, but the comment
   could mislead). Rewritten to describe fragments-write-files + creator/mutator.
2. **Procfile-only formation `source` (minor, FIXED).** Prose implied but didn't
   state the synthesized formation is `source:"procfile"`; LLM resolved it via
   the schema enum. Tightened to say it explicitly.
3. **Mild over-engineering for the 2-discoverer case (accepted, by design).**
   The LLM noted a single flat file would be lighter *for this fixture* (4 files
   vs 1), since both triggers fired so it paid file-hopping without the skip
   benefit. Correct observation — but the structure is the right call for the
   general case (gcp's large multi-artifact fragments, trigger-gated loading,
   reuse). The interpreter already acknowledges single-job phases are "one
   fragment + no-op assembler." Kept.

## Net

The full three-kind taxonomy (phase / fragment / assembler) is implemented and
cold-validated on discover: single creator per artifact, assembler-only
mutation, fragments self-describing and independently checkable, postconditions
correctly placed. The `_reads`/`_mutates`/`_produces` assembler triad is the
clarifying core. Two defects fixed; the over-engineering note is an accepted
tradeoff for the gcp-scale general case. This taxonomy now generalizes to every
later phase (clarify = 1 fragment + no-op assembler; generate = multi-fragment +
multi-artifact assembler).
