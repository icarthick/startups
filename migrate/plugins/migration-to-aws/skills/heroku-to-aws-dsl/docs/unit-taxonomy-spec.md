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

| Kind | Role | Reads | Writes |
|---|---|---|---|
| **Phase** | lifecycle + composition | — | — (composes the units below) |
| **Fragment** | one unit of work, single responsibility | source inputs | 1..N phase artifacts (directly to disk) |
| **Assembler** | combine / enrich fragment outputs | fragment artifacts | mutates 0..N + creates 0..N artifacts |

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
responsibility (one source / one *reason to change* — they change together).
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
`_trigger` lives in the PHASE's `_fragments` list, NOT in the fragment. *When a
fragment fires* is a composition decision the phase owns; *what a fragment
promises and must satisfy* is the fragment's own contract. Reading the phase
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
