# DSL Unit Taxonomy — Phase / Fragment / Assembler

Status: SPEC (agreed in design discussion 2026-06-27). This is the fixed target
for reshaping discover and authoring all later phases. The interpreter and phase
files must conform to this.

## Why three kinds

A phase's executable body decomposes into **fragments** (units of discovery/work)
plus exactly one **assembler** (the unit that combines/enriches fragment outputs
into the phase's final artifacts). Earlier the body was a flat `_steps` list, or
a `_routes` list that blurred "do work" and "combine work" into one kind. The
three-kind model separates concerns that have genuinely different contracts:

| Kind          | Role                                    | Reads              | Writes                                  |
| ------------- | --------------------------------------- | ------------------ | --------------------------------------- |
| **Phase**     | lifecycle + composition                 | —                  | — (composes the units below)            |
| **Fragment**  | one unit of work, single responsibility | source inputs      | 1..N phase artifacts (directly to disk) |
| **Assembler** | combine / enrich fragment outputs       | fragment artifacts | mutates 0..N + creates 0..N artifacts   |

## Core rules

### 1. Fragments write artifacts directly (to disk)

Fragments do NOT hold output only in memory. They WRITE their artifact file(s)
to `$MIGRATION_DIR/`. Rationale: real discovery outputs (e.g. gcp's
`gcp-resource-inventory.json`) are large; forcing them through in-memory
accumulators until a final writer is wrong for big data. (This walks back the
earlier "fragments never write files" rule — that was a heroku-small assumption
that breaks on gcp-scale data.) Files here are NOT engine-style intermediate
plumbing; they are the phase's actual artifacts.

### 2. A fragment produces 1..N artifacts, from ONE responsibility

A fragment may write multiple files, but ONLY if they derive from its single
responsibility (one source / one _reason to change_ — they change together).
Example: gcp `discover-terraform` produces BOTH `gcp-resource-inventory.json`
and `gcp-resource-clusters.json`, because clusters is derived from the inventory
resources in the SAME terraform parse — one source, one reason to change.

**Reason-to-change guard (prevents the multi-artifact loophole):** outputs with
INDEPENDENT sources or independent reasons-to-change MUST be separate fragments
(e.g. heroku terraform-discovery vs billing-discovery — two sources, two reasons,
two fragments). The test is NOT "two files → two fragments"; it is "two reasons
to change → two fragments."

### 3. NO inter-fragment dependencies

Fragments are an independent, flat, freely-orderable set. A fragment NEVER reads
another fragment's output. If output B is derived from output A, that coupling is
a SIGNAL they belong in the SAME fragment — not two fragments with a dependency
edge. "I need a dependency between fragments" is a design smell meaning the split
is wrong. This keeps fragments a flat set (no DAG, no ordering contract, no
dependency-resolution conformance).

### 4. Exactly one assembler per phase (mandatory; may be no-op)

Every phase has exactly one assembler, and it is terminal. Its job spans a
spectrum:

- **merge/transform**: read several fragment artifacts → combine into one file.
- **enrich in place**: mutate a fragment-written file (add cross-references, etc.).
- **derive**: create new cross-cutting files from fragment artifacts.
- **promote/no-op**: when fragments already wrote the phase's artifacts and
  nothing needs combining, the assembler just validates them (its postconditions
  ARE the phase's artifact-level contract — so it earns its existence even as a
  no-op).

The assembler is the consistent home for the **artifact-level contract** of any
file it touches.

### 5. Creator / mutator ownership over time (in-place mutation is allowed)

An artifact has exactly ONE **creator** (a fragment OR the assembler) and
zero-or-more **mutators** (the assembler only). The creator asserts the file's
INITIAL contract at creation; the assembler asserts the FINAL contract after any
mutation. Whoever LAST writes a file owns its final postconditions.

CI conformance: every phase artifact has exactly one creator; only the assembler
appears as a mutator; phase `_produces` == union of (fragment `_produces`) ∪
(assembler `_produces`) ∪ (assembler `_mutates`).

### 6. Closed vocabulary extends into ALL unit files

Fragment files and the assembler file are first-class DSL units with their own
frontmatter — NOT anonymous markdown. Every `_`-key in any unit's frontmatter or
`meta` fences must be in the interpreter vocabulary; a typo'd key fails loudly
(Golden Rule 4) in a fragment exactly as in a phase. This is what makes the unit
files structurally testable (the gap the route-refactor had introduced).

## Postcondition placement

- **Fragment postconditions** check the file(s) THAT FRAGMENT writes, at write time.
- **Assembler postconditions** check the files it creates, and the FINAL state of
  files it mutates.
- **Phase postconditions** check only cross-cutting / lifecycle invariants that
  belong to the phase as a whole (rare; most artifact checks live in the unit
  that last wrote the file).

## Frontmatter key-sets

### Phase (lifecycle + composition)

`_phase`, `_title`, `_requires_phase`, `_scope`, `_input`, `_init` (first phase),
`_re_entry_guard`, `_preconditions`, `_fragments` (ordered list, each
`{_id, _trigger, _file}`), `_assemble` (`{_file}` — mandatory), `_postconditions`
(phase-level only), `_produces` (full artifact set = union), `_advances_to`,
`_forbids_files`, `_on_error`.

### Fragment (one responsibility → 1..N artifacts)

`_fragment` (id), `_of_phase`, `_scope`, `_produces` (the file(s) it creates),
`_preconditions` (optional, fragment-local), the body (`## Step:` sections),
`_postconditions` (on its own artifacts), `_on_error`.

### Assembler (combine / enrich → mutate and/or create)

`_assemble` (id), `_of_phase`, `_scope`, `_reads` (fragment artifacts consumed),
`_mutates` (files edited in place, 0..N), `_produces` (new files created, 0..N),
the body, `_postconditions` (on mutated + created files), `_on_error`.

## Trigger ownership

`_trigger` lives in the PHASE's `_fragments` list, NOT in the fragment. _When a
fragment fires_ is a composition decision the phase owns; _what a fragment
promises and must satisfy_ is the fragment's own contract. Reading the phase
tells you "what runs when"; reading a fragment tells you "what it produces + must
satisfy."

## Worked example A — heroku discover (independent sources, merge)

Two responsibilities (parse IaC vs parse invoices) → two fragments:

- fragment `terraform` (trigger: always/required) → writes its resource data
- fragment `billing` (trigger: glob billing files) → writes its billing data
- assembler → merges into ONE artifact `heroku-resource-inventory.json`
  (billing as a section). Today heroku's outputs are small; the assembler
  merge-into-one is the natural shape.

## Worked example B — gcp discover (one source, multi-artifact fragment)

- fragment `terraform` (one responsibility: parse GCP terraform) → writes BOTH
  `gcp-resource-inventory.json` AND `gcp-resource-clusters.json` (clusters
  derived from inventory in the same parse — one reason to change, so NOT split).
- (other gcp discover fragments for their own sources, each writing their files)
- assembler → may enrich `gcp-resource-inventory.json` in place and/or derive
  cross-cutting files; validates the final set.

The gcp case is why fragments write files (big data) and why a fragment produces
1..N artifacts (inventory+clusters from one source) rather than being split into
dependent fragments.

## Conformance checklist (CI)

1. Every phase has exactly one `_assemble`; it is terminal.
2. Every phase artifact (`_produces`) has exactly one creator (a fragment or the
   assembler).
3. Only the assembler appears in any `_mutates`.
4. Phase `_produces` == union of fragment `_produces` + assembler
   `_produces`/`_mutates`.
5. No fragment reads another fragment's artifact (no inter-fragment deps).
6. Every `_file` resolves; every unit file parses; closed-vocab holds in all.
7. Each artifact's final postconditions live with its last writer.
8. Reason-to-change guard: multi-artifact fragments justified (same source).

## Knowledge / contract / procedure separation

Status: SPEC (agreed 2026-06-28). A unit's `.md` file is PROCEDURE. Data that
can evolve independently of the procedure MUST NOT be inlined in the procedure's
prose — it lives in a separate artifact the procedure references, so the two
version independently.

### The test (apply to every literal value or table in a unit file)

> **"Would someone change this value/table for a reason that has NOTHING to do
> with changing the mapping/algorithm itself?"**

- **YES → it is KNOWLEDGE.** Extract it to `knowledge/<skill>/...` (JSON DATA)
  and reference it from the procedure. Never inline it in `## Step:` prose.
- **NO → it is PROCEDURE.** It is the algorithm/branch/order/error-policy and
  stays in the `.md`.

A third category is neither: the **output CONTRACT** (the shape of the artifact a
unit produces) lives in `schemas/*.json`. It is not knowledge (no one tunes it on
an independent cadence) and not procedure (it is a shape, not a step) — so it is
NOT extracted to a "template" file. The procedure REFERENCES the schema; it does
not re-list every field. (Re-listing creates an MD↔template↔schema drift surface
— strictly worse.)

A fourth home covers GENERATED OUTPUT skeletons: **templates** in
`templates/<phase>/...` (e.g. HCL `.tf.tmpl`, markdown/doc templates, shell
scripts). When a phase's job is to EMIT files (generate), the body of those files
is parameterized boilerplate that evolves independently of the routing algorithm
(a provider-version bump, a tag change, a reworded guide section) — so it is
DATA, like knowledge, and lives outside the procedure. The fragment is the
ROUTING ALGORITHM (which template fires for which input, how vars are filled);
the templates are referenced via `_templates`, not inlined. Placeholders are
`{{key}}`; "emit exactly one of N variants" = named template blocks/files the
routing selects; repetition = a documented REPEAT marker. (Distinction from
knowledge: knowledge is LOOKUP DATA consumed to compute a value; a template is an
OUTPUT skeleton emitted to disk. Both are referenced, never inlined.)

### The three homes

| Category      | Test result                             | Home                              | Example                                                                                                                                                                                              |
| ------------- | --------------------------------------- | --------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Knowledge** | changes independently of the algorithm  | `knowledge/<skill>/*.json`        | dyno→Fargate table; Postgres `engine_version`; new_vpc CIDR/subnet plan; service ports (5432/6379/9092); the 0–100 clamp bound; default region lists; validation regexes; the clarify defaults table |
| **Procedure** | changes only when the algorithm changes | the unit `.md` (`## Step:` prose) | "look up dyno_type, exact case-insensitive"; "if web also emit ALB"; "do not recompute from provenance"; branch/order/error policy                                                                   |
| **Contract**  | the produced artifact's shape           | `schemas/*.json`                  | `aws-design.schema.json`; `preferences.schema.json`. The MD references it; it does not re-list fields.                                                                                               |

### Tunable-constants sheet (avoid lonely scalar files)

Do NOT scatter one-value files. Loose per-skill constants that pass the test
(engine versions, the VPC CIDR/subnet plan, service ports, clamp bounds, default
region) collect into ONE per-phase sheet, e.g.
`knowledge/<skill>/design/design-defaults.json` — "the knobs an org turns
without rewriting the migration." A single coherent sheet earns its file; a
lonely scalar does not.

### The guardrail (do NOT over-extract)

Extract DATA and TUNABLE CONSTANTS; NEVER extract LOGIC or CONTRACT. The failure
mode is a hollow `.md` of "look up X in file Y" with the actual algorithm
fragmented across JSON so the procedure is no longer readable AS a procedure.
The test is the guardrail: the dyno TABLE is data (extract); the clamp BOUND is a
tunable constant (extract); the "if web emit ALB" BRANCH is logic (keep); the
output SHAPE is contract (schema). Hold that line and the `.md` stays readable as
an algorithm while the JSON stays meaningful as knowledge.

### No-duplication rule

A datum lives in exactly ONE place. If a value is in a knowledge JSON, the
procedure references it — it does NOT re-state it (e.g. do not write "(0–100)"
in prose when `_desired_count.min/max` already holds it; do not re-type a
per-table `_on_not_found` message the JSON already carries). Duplication is a
drift surface and a conformance failure.

### Conformance checklist (CI) — knowledge separation

(Global conformance checks 9–12, continuing the lists above. ENFORCED by
`scripts/validate_dsl.py`, wired into `mise run lint` / `build`.)

1. No bare literal in `## Step:` prose that is a tunable constant (engine
   version, CIDR, port, clamp bound, region, regex) — such values MUST resolve
   to a `knowledge/` reference. (Heuristic-flag: numeric/version/CIDR/port
   literals in step prose are candidates for review.)
2. No datum appears in BOTH a knowledge JSON and step prose (no-duplication).
3. The output artifact's field set is asserted by a `schemas/*.json` the
   assembler `_validate_schema`s against — the MD does not re-enumerate it as
   the authority.
4. Every `knowledge/` file is referenced by at least one unit (no orphan data);
   every `_knowledge` reference resolves (no dangling reference).
5. **Cross-table key coverage.** When one phase's knowledge table EMITS a value
   that a LATER phase's table must look up by (e.g. design's
   `postgres-rds-sizing.json` emits an `rds_instance_class` that estimate's
   `aws-pricing.json` must have a rate for), EVERY value the producer can emit
   MUST exist as a key in the consumer table. (Surfaced by the real-repo run:
   design emitted `db.m6g.*` RDS classes the estimate table lacked → silent
   `unpriced`. The structural gates can't catch a legitimately-`unpriced` line;
   this consistency check is the guard.)
6. **Single load owner.** `_knowledge`/`_templates` `_when` guards exist ONLY in
   phase frontmatter — a step `meta` block may carry `_knowledge`/`_templates`
   but those entries carry NO `_when` and are USES annotations, never a second
   load decision.
7. **Uses-subset.** Every file named in any step's `_knowledge`/`_templates`
   MUST be declared in its phase's `_knowledge`/`_templates` (a step may not
   reference a file the phase doesn't know about). Catches the
   guard-vs-step contradiction statically.
8. **Guard scope.** Every phase `_when` guard references ONLY the phase's
   `_input` artifacts (inventory, preferences, source globs) — never a fragment
   output or an in-run-computed value (which wouldn't exist when the guard is
   evaluated). Makes "does the LLM have enough to evaluate the guard?" a
   checkable property (guard mentions only `_input`).

## Unit file regions (whole-file grammar)

Status: SPEC (agreed 2026-06-28). Every unit file has NO undefined zones — each
region is a named thing the interpreter (`INTERPRETER.md` → "Unit file regions")
has a rule for. The shape is:

```
---  frontmatter (STRUCTURAL contract)  ---
# <H1 title>                 ← cosmetic, no meaning
## Orientation               ← exactly one, NON-NORMATIVE reader context
## Step: <id>                ← zero or more, the executable procedure
  (a phase with pure-composition work has ZERO steps)
```

Three content homes, no overlap (this is the file-structure analogue of the
knowledge/contract/procedure split):

- **Contract** → frontmatter (the only source of truth for scope, IO, produces).
- **Orientation** → the one `## Orientation` section: descriptive, get-your-
  bearings prose; the interpreter reads it but never executes it; it carries no
  rule.
- **Procedure** → `## Step:` bodies.

Why named, not positional: an author can miss "whatever sits before the first
step"; a named `## Orientation` heading cannot be accidentally absorbed and is
structurally verifiable. Why no trailing sections: a `## Output`/`## Scope`/
`## Notes` after the steps just restates `_produces`/`_scope` — duplication and a
drift surface (same no-duplication rule as knowledge). Scope lives in `_scope`,
outputs in `_produces`/step `_writes`; nowhere else.

### Conformance checklist (CI) — unit file regions

(Global conformance checks 13–17, continuing the lists above.)

1. A unit file is exactly: frontmatter, then an optional H1, then at most ONE
   `## Orientation`, then zero-or-more `## Step:` sections — and nothing else.
   Any other top-level section (`## Output`, `## Scope`, `## Notes`, …) is a
   defect.
2. `## Orientation`, if present, sits immediately after the H1 and before the
   first `## Step:`; there is at most one.
3. No normative language (MUST / NEVER / "do NOT" imperatives that bind
   behavior) appears in the H1 or `## Orientation` — binding rules live in the
   frontmatter or a `## Step:`. (Heuristic-flag for review.)
4. Nothing appears after the last `## Step:` (or after `## Orientation` when a
   unit has no steps).
5. **No interpreter-rule restatement in a `## Step:` body.** A step body is
   fragment-SPECIFIC procedure; it must NOT re-state a universal interpreter
   rule as if it were a local instruction (e.g. "the phase _knowledge is the sole
   load decision; the step list is a USES annotation", "advance only after
   HANDOFF_OK", "load only the guard-true tables"). The interpreter already
   applies those everywhere; restating them is duplication AND a drift surface
   (it is how a step's prose can silently contradict the contract — e.g. a step
   saying "load" when the phase guard owns loading). Authors write only what is
   unique to the step. (Orientation MAY descriptively recap contract behavior
   when it points at the authoritative key — that is reader-orientation, not a
   step re-legislating. Heuristic-flag: load/gate/advance rule-language in a step
   body.)
