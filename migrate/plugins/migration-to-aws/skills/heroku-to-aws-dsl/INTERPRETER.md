# How to Execute a Migration Phase DSL (`*.phase.yaml` or `*.phase.md`)

You are executing a migration phase defined declaratively in a `*.phase.yaml`
file (pure-YAML form) or a `*.phase.md` file (FORM 2b — YAML frontmatter + step
bodies in markdown; see the FORM 2b section below). This document is the INTERPRETER: it tells you what each `_`-prefixed key
means and what action to take. It is SKILL-AGNOSTIC and SHARED across every
phase of every migration skill — read it ONCE, then execute any phase file.

**Core contract:** keys starting with `_` are DSL vocabulary defined here. Keys
NOT starting with `_` are author content (prose, file paths, schema names) —
treat them as data/instructions, not as commands. If you encounter a `_`-key
NOT defined in this document, STOP and report it (the file is invalid — CI
should have caught this).

You execute the phase TOP TO BOTTOM in this order:
`_init` (first phase only) → `_re_entry_guard` → `_preconditions` →
**read `_input` content + evaluate `_knowledge`/`_templates` guards and load the
guard-true files** → the `_fragments` (in listed order, skipping false triggers;
each WRITES its artifacts) → the `_assemble` unit (reads/mutates/creates files)
→ `_postconditions` → (on full pass) advance per `_advances_to`.

A phase composes its work from `_fragments` + exactly one `_assemble` (see the
unit-taxonomy section below). Fragment and assembler files are first-class DSL
units with their own frontmatter.

`_re_entry_guard` is a top-level phase key (sibling of `_preconditions`),
evaluated in that position — BEFORE the steps — because its job is to stop a
re-run before it overwrites this phase's own artifact. See its section below.

---

## Phase identity

- `_phase` — the phase name. Used in all diagnostics: `GATE_FAIL | phase=<_phase> | ...`.
- `_title` — human label. Cosmetic.
- `_requires_phase: X` — before doing ANYTHING, read `.phase-status.json` and
  confirm `phases.X == "completed"`. If not, emit
  `GATE_FAIL | phase=<_phase> | field=phases.X | reason=missing`, do NOT modify
  `.phase-status.json`, and tell the user to complete phase X first.
- `_scope` — the phase's ONLY job. You MUST NOT produce anything outside it.
  Treat it as a hard boundary.

## `_input`

A list of artifact filenames this phase consumes from `$MIGRATION_DIR/`.
**Load timing:** immediately AFTER `_preconditions` pass (which enforce the
inputs EXIST + parse), read every `_input` artifact's CONTENT into context —
before evaluating `_knowledge`/`_templates` guards and before running the
fragments. (Earlier wording said "read them during the steps"; that is too late
— the `_when` guards are predicates over input CONTENT, so the content must be
in context first. Existence-only is not enough to evaluate a guard.) Glob
patterns (e.g. `**/*.tf`) are workspace-relative source files the phase reads
directly rather than run artifacts.

## `_init`

A block of one-time setup actions to run BEFORE `_preconditions`, present only on
the FIRST phase of a migration (the one with `_requires_phase: null`). Verbs:

- `_init_migration_run: true` — establish `$MIGRATION_DIR`:
  1. Check for an existing `.migration/` dir at the project root. If runs exist,
     list them with their phase status and ask the user: `[A] Resume latest`,
     `[B] Start fresh`, `[C] Cancel`. On resume, set `$MIGRATION_DIR` to the
     chosen run and read+validate its `.phase-status.json` (apply the re-entry
     guard if this phase already completed).
  2. On fresh / no existing runs: create `.migration/[MMDD-HHMM]/` (current
     timestamp) and set `$MIGRATION_DIR` to it.
  3. Create `.migration/.gitignore` (if absent) containing exactly:
     `# Auto-generated migration state (temporary, do not commit)` / `*` /
     `!.gitignore`.
  4. Write `.phase-status.json` with all six phases (`discover`, `clarify`,
     `design`, `estimate`, `generate`, `feedback`) — this phase `in_progress`
     and `current_phase` set to it, the rest `pending`.
     Run this BEFORE `_preconditions` because the preconditions/steps read and
     write inside `$MIGRATION_DIR`, which must exist first.

## `_preconditions`

A list of checks to run BEFORE any step. Each item is one check verb plus an
`_on_failure` action (see ERROR ACTIONS). Run them in order; on the first
failure, perform its `_on_failure` action and STOP (do not run steps). Check
verbs:

- `_check_phase_completed: X` — `.phase-status.json → phases.X == "completed"`.
- `_check_single_active_phase: true` — at most one core phase is `"in_progress"`.
- `_check_file_exists: <path>` (or a list) — file(s) exist in `$MIGRATION_DIR/`.
- `_validate_json: <path|list>` — file(s) parse as valid JSON.
- `_validate_schema: {file, schema}` — file validates against the named JSON
  Schema (resolve `schema` relative to the skill's `schemas/` dir).
- `_check_source_exists: {glob, containing}` — at least one workspace file
  matching `glob` exists AND (if `containing` is given) contains that literal
  substring. Used for SOURCE inputs (e.g. `.tf` files with `heroku_` blocks),
  not run artifacts. On failure, perform its `_on_failure`.

When preconditions pass, set `phases.<_phase> = "in_progress"` and
`current_phase = <_phase>` in `.phase-status.json` (read-merge-write), then proceed.

## `_knowledge`

Data files the phase MAY reference (lookup tables, tunable-constant sheets).
Declared ONLY in the PHASE frontmatter. Each item is `{file, _when}`.

**The phase `_knowledge` is the SOLE load decision.** A `file` enters context
IFF its `_when` guard is true; a bare `file:` (no `_when`) always loads. Evaluate
guards right after `_input` is read (see `_input` load timing), BEFORE the
fragments run. Do NOT load guard-false files — they're irrelevant and waste
context. Once a file is in context, NEVER re-read it.

**Guard scope (so the LLM always has enough to evaluate it):** a `_when` guard
MAY reference ONLY the phase's `_input` artifacts (inventory, preferences, source
globs) — which are in context by the time guards are evaluated. A guard MUST NOT
reference a fragment's output, an `_assemble` result, or any value computed later
in the run (the LLM cannot evaluate what doesn't exist yet). If a load decision
depends on a derived value, the file isn't phase-knowledge — rethink the split.

**Step-level `_knowledge` is a USES annotation, NOT a second load decision.** A
`## Step:` `meta` block may carry `_knowledge: [files]` to declare "this step
consults these (already-loaded) files." It NEVER triggers a fetch and NEVER
overrides a phase guard: a step naming a file whose phase guard was false this
run simply does not use it on that branch (the file is not in context). Every
file a step lists MUST be declared in the phase `_knowledge` (CI-checkable
subset rule — see the conformance checklist). This single-owner split is why the
phase guard and a step list can never contradict: one loads, the other only
uses.

**The `[_uses: <file>]` prose marker.** When a step's PROSE references a
structure-owned file (a knowledge/template/schema file), it MUST tag the
reference with an inline marker binding it back to the step's `meta`
`_knowledge`/`_templates`:

> Look up `config.dyno_type` in `dyno-fargate-sizing.json.rows` `[_uses: dyno-fargate-sizing.json]`

The marker (a) keeps the domain sentence readable (the reference stays inline,
not lifted into a field) while (b) making the reference a CHECKABLE link, not
free-floating prose. CI enforces: every `[_uses: F]` names a file declared in
that step's `meta` `_knowledge`/`_templates`; and a bare backtick filename in a
step body that is NOT tagged is a violation (that untagged-ref is the drift
surface — it can name a file the structure doesn't own / a guard suppressed).
The author still writes pure domain logic; the marker is the structural tether,
not extra meta-prose. (Filenames that are themselves the step's `_writes`/
`_produces` output, or appear inside fenced code blocks, are not `_uses`
references and are not tagged.)

## `_templates`

Output-skeleton files (in `templates/<phase>/...`) the phase EMITS to disk,
filling `{{key}}` placeholders — HCL `.tf.tmpl`, doc/markdown templates, shell
scripts. Same loading contract as `_knowledge`: declared in the PHASE frontmatter
as the sole load decision (`{file, _when}`, guard-scope = `_input` only, loaded
before the fragments, never re-read); a step `_templates` list is a uses-subset
annotation, never a second load. Reference-don't-inline. A template is DATA (an
output skeleton), distinct from knowledge (lookup data consumed to compute a
value): a generate fragment is the ROUTING ALGORITHM selecting + filling
templates; the templates carry the boilerplate. "Emit exactly one of N variants"
= the routing selects a named template; repetition within a template uses a
documented `REPEAT` marker.

## `_on_error`

A top-level REFERENCE TABLE mapping each error-action name (`_halt_and_inform`,
`_warn_and_skip`, `_defer`, `_default_and_warn`, `_unrecoverable`) to its
documented effect + status transition. It is NOT executed directly and is NOT a
step — it documents the canonical meaning of the actions that `_on_failure` and
in-prose actions resolve to (see ERROR ACTIONS). Treat it as documentation; the
ERROR ACTIONS section below is authoritative for behavior.

## Phase body: `_fragments` + `_assemble` (the unit taxonomy)

A phase composes its work from **fragments** (units of work, each its own file)
plus exactly ONE **assembler** (combines/enriches fragment outputs into the
phase's final artifacts). Both fragment and assembler files are first-class DSL
units with their OWN frontmatter and `## Step:` bodies (FORM 2b) — the closed
vocabulary applies inside them too (a typo'd `_`-key fails there exactly as in a
phase). The phase composes them; it does not inline their work.

(A phase whose work is a single linear job is still modeled this way: one
fragment + a no-op/promote assembler. There is no separate flat-`_steps` phase
body mode — uniformity across all phases.)

### `_fragments` (in the PHASE frontmatter)

An ordered list; each entry composes one fragment:

- `_id` — fragment name.
- `_trigger` — WHEN this fragment runs (the phase owns triggering, not the
  fragment). One of: `_always: true`; `_glob: <pattern|list>`;
  `_artifact_exists: <name|list>`; `_check_source_exists: {glob, containing}`;
  `_when: <plain-language condition>` (evaluated against the phase inputs /
  preferences — use this when a fragment is gated on a VALUE in an input rather
  than the presence of a file/artifact, e.g. an opt-in preference selecting an
  alternate compute branch).
  A false trigger SKIPS the fragment (its artifact(s) simply absent; the
  assembler accounts for absence).
- `_file: <path>` — the fragment file. Load ONLY when the trigger is true
  (context economy — an untriggered fragment's file is never read).

### Fragment file frontmatter (`_file` target)

A fragment is ONE responsibility producing 1..N artifacts WRITTEN DIRECTLY to
`$MIGRATION_DIR/`. Keys:

- `_fragment` — id (matches the phase's `_fragments[]._id`).
- `_of_phase` — the owning phase (self-describing back-reference).
- `_scope` — this fragment's hard boundary.
- `_produces: [files]` — the artifact file(s) it CREATES. May be >1 ONLY if they
  derive from the same source / one reason-to-change (e.g. gcp inventory +
  clusters from one terraform parse). Outputs with independent sources/reasons
  MUST be separate fragments. A fragment NEVER reads another fragment's output
  (no inter-fragment dependencies — if B derives from A, they are ONE fragment).
- `_preconditions` — (optional) fragment-local checks.
- body: `## Step:` sections (per `_steps` rules below) that WRITE `_produces`.
- `_postconditions` — checks on the file(s) THIS fragment wrote, at write time.
- `_on_error`.

### Assembler file frontmatter (the phase's `_assemble._file`)

Exactly one per phase, terminal. Combines/enriches fragment artifacts. Keys:

- `_assemble` — id.
- `_of_phase`, `_scope`.
- `_reads: [files]` — the fragment artifacts it consumes. A validator/no-op
  assembler MAY also read the phase's own `_input` artifacts (e.g. the discover
  inventory) when it needs them to evaluate a CONDITIONAL contract — "value X is
  required only if the inventory contained resource Y." That is legitimate: the
  assembler owns the artifact-level contract, and some of those checks are
  trigger-dependent, so it must see the trigger source. It is still combine/
  validate, not new discovery.
- `_mutates: [files]` — (0..N) fragment artifacts it edits IN PLACE.
- `_produces: [files]` — (0..N) NEW files it creates.
- body: `## Step:` sections.
- `_postconditions` — on the files it CREATES and the FINAL state of files it
  MUTATES.
- `_on_error`.
  The assembler may be a no-op/promote (fragments already wrote the phase's
  artifacts, nothing to combine) — it still owns the artifact-level contract via
  its `_postconditions`, so it always exists.

### Creator / mutator ownership (in-place mutation allowed)

Each artifact has exactly ONE creator (a fragment OR the assembler) and 0..N
mutators (the assembler only). The creator asserts the file's INITIAL contract;
the assembler asserts the FINAL contract of anything it mutates. Whoever LAST
writes a file owns its final postconditions. The phase's `_produces` ==
union of all fragment `_produces` + assembler `_produces` + assembler
`_mutates`.

### Execution

Run fragments in `_fragments` order (skipping false triggers), each WRITING its
artifact(s) to disk. Then run the assembler, which reads/mutates/creates files.
Then the phase `_postconditions` (cross-cutting only). Fragments write files
directly (NOT in-memory-only) — real discovery outputs are large; these are the
phase's actual artifacts, not engine-style intermediate plumbing.

## `_steps` (the body grammar inside a fragment or assembler file)

An ordered list. Execute each step in order. A step has:

- `_id` — step name (for diagnostics/logs).
- `_reason: <prose>` — **the instruction you carry out using your own
  judgment.** This is where the real work lives. Do EXACTLY what it says,
  applying lookups from the loaded `_knowledge`. Be deterministic: a lookup is a
  lookup, a clamp is a clamp — do not improvise values the prose/knowledge
  dictate.
- `_knowledge: [files]` — (optional) the knowledge (DATA) file(s) THIS step uses.
- `_for_each: <collection>` — (optional) run the step body once per item in the
  named collection, in input order.
- `_branch_on: <field>` + `_cases: {value: {...}}` — (optional) within the
  iteration, branch on the item's field; run the matching case's body. Unlisted
  values are skipped (unless a `_default` case is given).
- `_collect: [names]` — (optional) declares the accumulator lists this step
  appends to (e.g. `services`, `warnings`), maintained across the iteration.
- `_writes_var: <name>` — the step produces in-run STATE (not a file) that later
  steps reference by that name (e.g. `compute_mode`).
- `_writes: <filename>` — the step writes that artifact to `$MIGRATION_DIR/`.
- `_when: <condition>` — (optional, step-level) run this step ONLY if the
  condition is true; otherwise skip it entirely.

## `_postconditions`

Checks run AFTER all steps, before advancing. Same check verbs as
`_preconditions`, plus:

- `_assert: <condition>` — the condition (plain language) MUST hold. On failure,
  perform its `_on_failure` if given, else emit
  `GATE_FAIL | phase=<_phase> | field=<the assertion> | reason=invalid` and halt.
- `_validate_schema: {file, schema}` — the produced artifact MUST validate.

(Re-entry is NOT a postcondition — it is the top-level `_re_entry_guard` key,
evaluated before the steps. See its own section above.)

If ALL postconditions pass, emit
`HANDOFF_OK | phase=<_phase> | artifacts=<_produces joined>`.
On ANY failure: emit the `GATE_FAIL` line, do NOT modify artifacts to force a
pass, do NOT advance, tell the user what failed and how to fix it.

## `_re_entry_guard`

A top-level phase key, evaluated BEFORE `_preconditions` and the steps (right
after `_init`). Re-running a phase whose outputs already drove downstream phases
would silently invalidate that downstream work, so this is the interlock that
stops it. Shape: `{if, action, reason, on_confirm}`.

If `if` is true (a downstream artifact already exists / a later phase completed),
perform `action` (normally `_halt_and_inform`) with `reason` and STOP — do NOT
run the steps, do NOT auto-delete anything.

This is a fail-closed interlock, NOT a cleanup: you NEVER destroy the user's
expensive downstream artifacts (e.g. the interactive `preferences.json`)
automatically just because an upstream phase was re-triggered. Re-running
discover is usually idempotent (same source files → same inventory), so the
downstream answers are often still valid; only the user knows whether this re-run
actually changes anything that matters. Surface the consequence and let them
decide.

ONLY if the user EXPLICITLY confirms the re-run, perform `on_confirm` — the
cascade reset — THEN run the phase normally (`_preconditions` → steps → ...):

- `on_confirm` (when present) names the reset. Its canonical meaning is: reset
  every phase DOWNSTREAM of `<_phase>` in the phase chain (`_advances_to`
  transitively) to `"pending"` in `.phase-status.json`, and remove the artifacts
  those downstream phases `_produces` from `$MIGRATION_DIR/`. Prior phases
  UPSTREAM of `<_phase>` are left untouched. This phase's OWN artifact is NOT
  removed — the re-run overwrites it.
- If a phase omits `on_confirm`, fall back to that canonical cascade derived from
  the phase chain. (Until the full phase chain is authored, a phase MAY spell out
  its concrete downstream artifact list inline so it is self-contained — see
  discover's guard.)
- The cascade is the ONLY place an interlocked re-run may delete downstream
  artifacts, and only post-confirmation. It does NOT violate Golden Rule 1 (that
  rule forbids mutating artifacts to make a gate PASS; this is an explicit
  user-authorized reset, surfaced first).

If `if` is false (normal first run), the guard is a no-op — proceed to
`_preconditions`.

## `_produces` / `_advances_to` / `_forbids_files`

- `_produces` — the artifact(s) this phase must have written (cross-checked
  against `_postconditions`).
- `_advances_to: X` — ONLY after `HANDOFF_OK`: set `phases.<_phase>="completed"`,
  `current_phase="X"`, update `last_updated`, write `.phase-status.json`. Then
  tell the user the phase is complete and which phase file to load next.
- `_forbids_files` — you MUST NOT create any file matching these patterns. All
  user communication is via output messages only.

---

## ERROR ACTIONS (the `_on_error` enum)

`_on_failure:` values, and the actions inside `_cases`/`_reason` like `_defer`,
resolve to these. The phase file's `_on_error:` block documents each one's
effect + status transition; the canonical behavior is:

- `_halt_and_inform: "<msg>"` — STOP the phase. Surface the message + a
  `GATE_FAIL` diagnostic. Status: retain `in_progress` (do NOT revert, do NOT
  advance).
- `_warn_and_skip` — append a warning, skip the CURRENT item, CONTINUE the loop.
- `_defer` — append an entry to the `deferred[]` accumulator (with the fields the
  schema requires), CONTINUE.
- `_default_and_warn` — apply the documented default value, append a warning,
  CONTINUE.
- `_unrecoverable` — STOP. Surface the error. Status: revert `phases.<_phase>`
  to `"pending"`, preserving all prior completed phases.

A `reason:` attached to a failure (e.g. `stale_downstream`) goes into the
diagnostic's `reason=` field.

---

## Step bodies in the markdown body (FORM 2b — seam-free hybrid)

When the phase file is a `.md` with YAML frontmatter and NO `_steps:` list in
the frontmatter, the steps live in the MARKDOWN BODY instead. In that case:

- Each step is a section headed `## Step: <id>`. Steps execute in the ORDER the
  `## Step:` sections appear in the body (top to bottom).
- Immediately under the heading, a fenced `` ```meta `` block holds the
  step's machine contract (the same `_`-keys you'd otherwise see inline:
  `_collect`, `_for_each`, `_branch_on`, `_when`, `_writes`, `_writes_var`,
  `_knowledge`). Parse it as YAML. Unknown `_`-keys there are invalid (Golden
  rule 4) exactly as in the frontmatter.
- Everything AFTER the `meta` block, until the next `## Step:` heading, is the
  step's `_reason` instruction prose. (There is no separate `_reason:` key in
  2b — the body prose IS the reason.)
- The contract and the instruction are therefore CO-LOCATED; there is no
  frontmatter step-list to correlate against. The frontmatter holds only the
  PHASE-level contract (identity, IO, preconditions, postconditions, knowledge,
  error policy, produces/advances/forbids).

Everything else (precondition/postcondition semantics, error actions, advancing)
is identical to the frontmatter-list form.

## Unit file regions (the whole-file grammar)

Every unit file (`*.phase.md`, fragment, assembler) is EXACTLY these regions, in
this order, and NOTHING else. There are no undefined zones — a region the
interpreter has no rule for is an invalid file (CI-flaggable, like an undefined
`_`-key).

1. **Frontmatter** (`---` … `---`) — the STRUCTURAL contract (identity, IO,
   preconditions, postconditions, knowledge, error policy, produces/advances/
   forbids, and for a phase the `_fragments`/`_assemble` composition). Machine-
   parsed, closed-vocabulary. This is the single source of truth for the unit's
   contract.
2. **An H1 title** (`# <name>`) — cosmetic, for humans. The interpreter assigns
   it no meaning.
3. **`## Orientation`** — exactly ONE such section, immediately after the H1.
   NON-NORMATIVE: it orients the reader (what this unit is, what it reads/writes,
   where its knowledge/contract live) and the interpreter READS it for context
   but MUST NOT execute it. It carries NO binding instruction — every rule lives
   in the frontmatter or a `## Step:`. A unit MAY omit Orientation; if present it
   is exactly one and only here. (Recap of contract behavior is allowed ONLY when
   it explicitly points at the frontmatter key that is the authority, e.g.
   "advances per `_advances_to`"; never as the source of a rule.)
4. **`## Step: <id>`** sections — zero or more, the executable procedure, run
   top-to-bottom (FORM 2b: each is an optional `` ```meta `` block then reason
   prose). A phase whose work is pure composition has ZERO steps (its work is the
   `_fragments`/`_assemble` declared in frontmatter); a fragment/assembler has
   one or more.

Nothing follows the last `## Step:` (or follows Orientation, when there are no
steps). Do NOT add trailing `## Output` / `## Scope` / `## Notes` prose — a
unit's scope is its frontmatter `_scope`, its outputs are `_produces` /
step `_writes`; restating them in trailing prose is duplication (a drift surface)
and is forbidden. Likewise no normative content may live in the H1 or
Orientation; if you wrote a rule there, move it into the frontmatter contract or
a `## Step:`.

## Golden rules

1. **Never modify an artifact to make a gate pass.** Gates are fail-closed.
2. **Never advance `.phase-status.json` except after `HANDOFF_OK`.**
3. **`_reason` prose is authoritative for HOW; the DSL is authoritative for the
   ORDER, the CONTRACTS, and the ERROR POLICY.** When prose and structure seem
   to conflict, the structure (preconditions/postconditions) wins — it's the
   guardrail.
4. **An undefined `_`-key means the file is invalid** — stop and report; do not
   guess its meaning.
5. **Stay inside `_scope`.** Producing out-of-scope output is a failure even if
   the steps "succeed."
6. **Only `## Step:` bodies and the frontmatter are executable.** The H1 and
   `## Orientation` are non-normative context — read them, never act on them. A
   file region the interpreter has no rule for (see "Unit file regions") makes
   the file invalid.
