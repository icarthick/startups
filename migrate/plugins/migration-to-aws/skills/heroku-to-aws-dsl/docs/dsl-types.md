# DSL Type System — a formal mirror of the DSL grammar

Status: IN PROGRESS (modeling exercise started 2026-06-28). This document
formalizes the DSL grammar that `INTERPRETER.md` defines in prose, as a set of
typed definitions. The goal is twofold:

1. **Deep understanding** — building the types IS an audit of the DSL. Every key,
   every closed value set, every "where can this appear" must be accounted for,
   which surfaces nuances, inconsistencies, and gaps in the grammar that prose
   never forces into the open.
2. **Complete validation** — the conformance validator (`scripts/validate_dsl.py`)
   is bounded by what it can model. A faithful, COMPLETE type mirror is the
   precondition for completely validating a DSL file. A partial model caps how
   much can ever be checked.

## Authoritative source

`INTERPRETER.md` IS the type system, written in prose. For each type, INTERPRETER
provides four things that map 1:1 onto a type definition:

| INTERPRETER provides (prose)                                                    | becomes (type)                     |
| ------------------------------------------------------------------------------- | ---------------------------------- |
| the allowed names / values                                                      | the enum / closed value set        |
| what each one does (behavior + status transition)                               | semantics doc on the type          |
| where the key may appear                                                        | the type's context / who embeds it |
| parsing notes ("treat as documentation", "run in order, stop on first failure") | the parsing/validation rules       |

Where the prose is precise, the type is a clean transcription. Where the prose is
vague, inconsistent, or silent, **that is a discovery** — recorded inline as a
`> NUANCE` / `> INCONSISTENCY` / `> DECISION` callout.

## The drift contract

These types DUPLICATE the grammar that lives in `INTERPRETER.md`. That coupling
is acceptable ONLY because it is finite, deliberate, change-together, and
self-catching — never silent:

- The type system MUST reject unknown `_`-keys (Golden rule 4). A DSL addition
  not mirrored here fails loudly the first time a file uses it.
- A future coverage check MUST assert the set of `_`-keys modeled here matches the
  set `INTERPRETER.md` declares. Divergence is a bug in one or the other.

## Implementation language

The canonical model is THIS document (language-agnostic prose + type sketches).
The enforcement is implemented in **TypeScript**, chosen for its type
expressiveness (discriminated unions + compiler-checked exhaustiveness) which
maps cleanly onto a DSL grammar.

- The validator is **CI/build-time only**. It NEVER runs when the plugin runs —
  the plugin is markdown/JSON files an LLM interprets; no Node/Python executes at
  plugin-run time. So there is no "runtime dependency" category here; the
  toolchain is purely dev/CI.
- **Zero npm deps to RUN.** Node 24 (already pinned in `mise.toml` for
  `markdownlint-cli2`/`dprint`) strips TypeScript types natively:
  `node scripts/validate_dsl.ts <skill-root>`. No `package.json`, no
  `node_modules` in tree.
- **Type-check gate:** `typescript` is added as a mise-managed npm CLI
  (`"npm:typescript"`, same mechanism as the existing markdownlint/dprint CLIs)
  and run as `tsc --noEmit` so the discriminated unions are compiler-verified.
- `mise.toml` is admin-owned (`@awslabs/startups-admins`): the `lint:dsl` task
  switch (python -> node) and the `npm:typescript` tool line must be flagged for
  their review. The change follows the repo's existing npm-CLI pattern.

### Toolchain conventions (proven 2026-06-28)

"Node-native type-strip (run) + `tsc --noEmit` (check)" coexist only under three
rules — every `.ts` file in the validator must follow them:

1. **Type-only imports use the inline `type` modifier:**
   `import { type ErrorAction, ERROR_ACTION_KINDS } from "./error-action.ts";`
   Node 24's stripper erases types; without `type` it tries to resolve a type as
   a runtime export and throws `does not provide an export named ...`.
2. **Relative imports keep the `.ts` extension.** Node's stripper does no
   extension resolution; `tsconfig` sets `allowImportingTsExtensions: true` so
   `tsc` accepts it (requires `noEmit: true`).
3. **`tsconfig.json`** at `scripts/dsl-validator/tsconfig.json` uses
   `module: esnext` + `moduleResolution: bundler` so `tsc` treats `.ts` as ESM
   WITHOUT needing a `package.json` — preserving the no-`package.json`,
   no-`node_modules`-in-tree property. Plus `strict`, `verbatimModuleSyntax`,
   `skipLibCheck`.
4. **No TypeScript parameter properties** (`constructor(readonly x: T)`). Node's
   strip-only mode rejects them (`ERR_UNSUPPORTED_TYPESCRIPT_SYNTAX`) because the
   shorthand requires CODE GENERATION, not just type stripping. Declare the field
   explicitly and assign in the constructor body. (Same reason: no enums with
   initializers that emit code, no namespaces — strip-only erases types, never
   generates runtime code.)
5. **Files using Node APIs** (`node:fs`, `process`) need `@types/node` for `tsc`
   to resolve them; the runtime is fine under Node 24. The CLI entry point will
   need `@types/node` added (dev-only) when built.

Run: `mise exec -- node scripts/dsl-validator/<entry>.ts <skill-root>`
Check: `cd scripts/dsl-validator && mise exec npm:typescript@5 -- tsc --noEmit`

## Type tiers (categories)

Types are organized by what kind of thing they ARE in the grammar. We define them
bottom-up (Tier 1 → 4): a composite cannot be understood until its parts are.

| Tier | Category                 | What it is                             | Examples                                  |
| ---- | ------------------------ | -------------------------------------- | ----------------------------------------- |
| 1    | **Value types**          | closed sets / atoms; depend on nothing | `ErrorAction`, trigger form, check verb   |
| 2    | **Entry / clause types** | one structured element inside a list   | `Guarded`, `FragmentRef`, `FailureClause` |
| 3    | **Sub-document types**   | a meaningful section of a file         | `Frontmatter`, `Step`, `Meta`             |
| 4    | **Unit types**           | a whole file                           | `Phase`, `Fragment`, `Assembler`          |

---

## Tier 1 — Value types

## Type 1: `ErrorAction`

**Source:** `INTERPRETER.md` §"ERROR ACTIONS (the `_on_error` enum)", lines 349–368;
appears-in note at line 351; `_on_error` reference-table note at lines 158–165.

**What it represents:** the closed set of five error-handling actions. An action
describes WHAT to do when a check/operation fails — its control-flow effect
(STOP vs CONTINUE), its phase-status transition, and any side effect.

**Shape — a tagged union (not a flat enum).** The two STOP variants
(`_halt_and_inform`, `_unrecoverable`) carry an OPTIONAL message — they SURFACE
text on failure. The three CONTINUE variants are nullary.

```
ErrorAction =
  | HaltAndInform { message?: str }   # STOP — optional surfaced message
  | WarnAndSkip                       # nullary (CONTINUE)
  | Defer                             # nullary (CONTINUE)
  | DefaultAndWarn                    # nullary (CONTINUE)
  | Unrecoverable  { message?: str }  # STOP — optional surfaced message
```

> CORRECTION (2026-06-28, evidence-driven): the ORIGINAL Type-1 model put message
> ONLY on `_halt_and_inform` (the other four nullary). The real DSL disproves
> that — `_unrecoverable` ALSO carries a block-scalar message in `_on_failure`
> carriers (`discover.phase.md:59`, `generate.phase.md:88`, `estimate.phase.md`),
> AND both STOP actions also appear BARE (`_on_failure: _unrecoverable` on
> asserts). So: message lives on the TWO STOP variants, OPTIONAL on each (bare
> forms omit it). The `tsc` compiler caught the original error when a probe built
> `_unrecoverable` with a message — the type system validating its own model.

**Per-variant semantics** (transcribed verbatim-in-meaning from lines 355–364;
documentation the type carries so checks can reason about an action without
re-reading prose):

| Variant             | control  | status_effect                         | side effect / scope               |
| ------------------- | -------- | ------------------------------------- | --------------------------------- |
| `_halt_and_inform`  | STOP     | retain `in_progress`                  | surface message + `GATE_FAIL`     |
| `_warn_and_skip`    | CONTINUE | none (spec silent → unchanged)        | append warning; skip CURRENT item |
| `_defer`            | CONTINUE | none (spec silent → unchanged)        | append entry to `deferred[]`      |
| `_default_and_warn` | CONTINUE | none (spec silent → unchanged)        | apply documented default; warn    |
| `_unrecoverable`    | STOP     | revert phase to `pending`, keep prior | surface error                     |

**Parsing rule (for the future parser):**

- A bare token in `{_warn_and_skip, _defer, _default_and_warn, _unrecoverable}`
  → that nullary variant.
- `_halt_and_inform: "<str>"` → `HaltAndInform(message=str)`. Missing/empty
  message = INVALID.
- Any other `_`-token in an action slot = INVALID (closed vocab, Golden rule 4).

**What this type does NOT own** (modeled on carrier/table types, later tiers):

- `reason` / `_reason` — a sibling diagnostic field on a failure clause, not a
  property of the action. (See NUANCE below — unresolved, parked.)
- the carrier keys themselves (`_on_failure`, a `_cases` entry's action,
  the `_on_error` documentation table).

**Carriers vs the documentation table — the load-bearing asymmetry:**

- `_on_failure:` (and a nested `_cases`/case action slot) HOLDS exactly one
  `ErrorAction`, to be PERFORMED. Executable. Resolves to one variant.
- `_on_error:` (phase block) does NOT hold one action — it is a REFERENCE TABLE
  enumerating the action names this phase uses → their `{effect, status}`. NOT
  executed; documentation only (lines 158–165). It is a SEPARATE type
  (defined at the phase tier), not a use of a single `ErrorAction`.

> DECISION (settled, as corrected): model `ErrorAction` as a TAGGED UNION; the
> two STOP variants carry an OPTIONAL `message`, the three CONTINUE variants are
> nullary. `_on_error` is NOT part of this type — it is a
> distinct phase-tier "documentation table" type. Both REFERENCE this enum;
> `_on_failure` carries one, `_on_error` describes many.
>
> NUANCE (parked): `reason:` (no underscore, line 367) is a sibling diagnostic
> field; `_reason` (underscore, line 351) is referenced as a place actions
> appear. These may be two different things (a diagnostic `reason=` field vs a
> step-prose `_reason`). Resolve when modeling the `FailureClause` (Tier 2) and
> step `Meta` (Tier 3) types. `ErrorAction` owns neither.
>
> NUANCE (spec silent): three variants have no explicit status-transition line;
> recorded as `status_effect: none (unchanged)` and marked inferred, rather than
> inventing a transition.

**Validation power this unlocks:**

- every action slot holds exactly one of these five (closed-set check);
- `_halt_and_inform` / `_unrecoverable` MAY carry a message; CONTINUE actions
  carry none (a message on a CONTINUE action = invalid);
- a per-item loop failure should not use `_unrecoverable` (control/scope mismatch
  — STOP action used where the loop semantics are CONTINUE-per-item);
- the `_on_error` documentation table's stated `{effect, status}` per action MUST
  match this canonical table (drift catch — the table restates these and could
  drift; ERROR ACTIONS is authoritative per line 165).

### Type 2: `CheckVerb`

**Source:** `INTERPRETER.md` §"`_preconditions`" (lines 84–93), §"`_postconditions`"
(lines 279–289).

**What it represents:** the closed set of CHECK verbs. A precondition/postcondition
item is "one check verb + an `_on_failure` action" — this type is the verb half
(the `_on_failure` half is `ErrorAction`, paired at the Tier-2 `Precondition`).
Each verb names a condition to test before steps (preconditions) or after, before
advancing (postconditions).

**Shape — a tagged union on the verb token.** The verbs have HETEROGENEOUS
argument shapes (a path-or-list, a phase name, a literal, a `{file, schema}`
object, a `{glob, containing?}` object, a plain-language string), so each variant
carries its own argument type. The verb token IS the discriminant (matches the
grammar: `_check_file_exists: foo.json` — key = verb, value = argument).

```
CheckVerb =
  | CheckPhaseCompleted    { phase: str }                  # _check_phase_completed
  | CheckSingleActivePhase                                 # _check_single_active_phase (arg `true` is vestigial -> nullary)
  | CheckFileExists        { paths: str | str[] }          # _check_file_exists
  | ValidateJson           { paths: str | str[] }          # _validate_json
  | ValidateSchema         { file: str, schema: str }      # _validate_schema
  | CheckSourceExists      { glob: str, containing?: str }  # _check_source_exists  (SHARED shape with trigger forms)
  | Assert                 { condition: str }              # _assert  (POST-ONLY)
```

**Per-verb metadata** (transcribed):

| Verb                         | argument              | context       | notes                                        |
| ---------------------------- | --------------------- | ------------- | -------------------------------------------- |
| `_check_phase_completed`     | phase name            | both          | `phases.X == "completed"`                    |
| `_check_single_active_phase` | `true` (vestigial)    | both          | ≤1 phase `in_progress`                       |
| `_check_file_exists`         | path or path[]        | both          | file(s) exist in `$MIGRATION_DIR/`           |
| `_validate_json`             | path or path[]        | both          | file(s) parse as JSON                        |
| `_validate_schema`           | `{file, schema}`      | both          | `schema` resolves under skill `schemas/`     |
| `_check_source_exists`       | `{glob, containing?}` | both          | ALSO a trigger form (shared type — parked)   |
| `_assert`                    | plain-language str    | **POST-ONLY** | implicit default-halt on failure (see below) |

**Parsing rule:** the YAML key is the verb token; its value is the argument,
parsed per the variant's shape. A key not in `CHECK_VERB_TOKENS` in a
pre/postcondition item = INVALID (closed vocab, Golden rule 4).

**What this type does NOT own:**

- the `_on_failure` pairing — modeled on the Tier-2 `Precondition` item.
- pre-vs-post LIST membership — a Tier-3 `Frontmatter` concern (this type only
  records each verb's ALLOWED context as metadata).
- the trigger-context use of `_check_source_exists` — the trigger type references
  this verb's argument shape (parked until trigger forms are modeled).

> DECISION (settled): tagged union on the verb token (mirrors `ErrorAction`);
> `_check_source_exists`'s `{glob, containing?}` shape defined HERE and SHARED
> with the trigger type; `context` (pre/post/both) encoded on the verb so
> "`_assert` is post-only" is data-driven; `_check_single_active_phase` is
> nullary (the `true` carries no information, dropped).
>
> NUANCE (`_assert` default failure): lines 281–283 — on failure with NO
> `_on_failure`, `_assert` emits `GATE_FAIL | reason=invalid` and halts. So it
> has an implicit default action the other verbs lack. Recorded as
> `defaultOnFailure` metadata on the `Assert` variant.
>
> INCONSISTENCY (minor): `_postconditions` says "same verbs as preconditions,
> plus `_assert`" yet re-lists `_validate_schema` (line 287). Treated as ONE verb
> usable in both contexts, not two.
>
> NUANCE (parked): `_check_source_exists` lives in TWO grammars (check-verb AND
> trigger form), same `{glob, containing?}` shape — like `_when`'s multi-context
> problem. Share the shape; resolve the mechanics when modeling trigger forms.

**Validation power this unlocks:**

- every pre/postcondition item's verb is one of these 7 (closed-set check);
- `_assert` may appear ONLY in `_postconditions` (context check);
- `_validate_schema`'s `schema` must resolve under the skill `schemas/` dir;
- `_check_source_exists`'s shape is consistent between its check-verb and trigger
  uses (cross-context shape check).

### Type 3: `Trigger` (and the `WhenCondition` atom)

**Source:** `INTERPRETER.md` §"`_trigger`" (lines 185–193).

**What it represents:** WHEN a fragment runs ("the phase owns triggering, not the
fragment"). Exactly ONE of 5 forms. A false trigger SKIPS the fragment — its
artifact(s) simply absent; the assembler accounts for absence (lines 192–193).

**Shape — a tagged union on `kind`** (uniform with `ErrorAction`/`CheckVerb`):

```
Trigger =
  | AlwaysTrigger                                    # _always (true vestigial -> nullary)
  | GlobTrigger              { patterns: str | str[] }    # _glob — workspace file(s) exist
  | ArtifactExistsTrigger    { names:    str | str[] }    # _artifact_exists — run artifact(s) exist
  | CheckSourceExistsTrigger { arg: SourceExistsArg }     # _check_source_exists — SHARED arg w/ CheckVerb
  | WhenTrigger              { when: WhenCondition }      # _when — plain-language value condition
```

**New shared atom introduced here:**

```
WhenCondition { condition: str }
```

The plain-language `_when` string. `_when` appears in THREE contexts — a trigger
(here), a step-level gate (line 277), and a `_knowledge` guard (`{file, _when}`).
All three are structurally a plain-language condition, so they SHARE this one
atom. What differs by context is the SCOPE the condition may reference (e.g. a
knowledge guard may reference only `_input`) — that is a CHECK (guard-scope), not
a shape difference.

**Form metadata** (transcribed):

| Form                   | argument              | tests                                     |
| ---------------------- | --------------------- | ----------------------------------------- |
| `_always`              | `true` (vestigial)    | always fires                              |
| `_glob`                | pattern or pattern[]  | workspace file matching glob exists       |
| `_artifact_exists`     | name or name[]        | run artifact in `$MIGRATION_DIR/` exists  |
| `_check_source_exists` | `{glob, containing?}` | source file matches glob (& substring)    |
| `_when`                | plain-language string | a VALUE in phase inputs/preferences holds |

**Parsing rule:** the YAML key is the form token; value parsed per the variant's
shape. A key not in `TRIGGER_KINDS` inside a `_trigger` = INVALID (Golden rule 4).

**What this type does NOT own:**

- guard-scope (which inputs/values a `_when` may reference) — a CHECK, per context.
- the `_fragments` entry that carries a `Trigger` — the Tier-2 `FragmentRef`.

> DECISION (settled): share only `SourceExistsArg` (the argument type) with
> `CheckVerb`, NOT the variant — `Trigger` has its own `CheckSourceExistsTrigger`
> member (distinct union, same arg shape). One shared `WhenCondition` atom across
> the three `_when` contexts (shape shared; scope-of-reference is a per-context
> check). `_always` is nullary (the `true` carries no info), consistent with
> `_check_single_active_phase`.
>
> NUANCE (`_glob` vs `_artifact_exists`): same arg SHAPE (`str | str[]`), distinct
> meaning — `_glob` = workspace SOURCE files, `_artifact_exists` = RUN artifacts in
> `$MIGRATION_DIR/`. Distinguished only by `kind` (that is what the discriminant
> is for). `_glob` vs `_check_source_exists`: latter adds `containing` + source
> semantics.

**Validation power this unlocks:**

- every `_trigger` is exactly one of these 5 (closed-set check);
- a `_when` trigger's condition references only evaluable scope (guard-scope, the
  shared `WhenCondition` makes this one check across all three `_when` uses);
- `_artifact_exists` names should match some phase's `_produces` (a future
  cross-phase artifact-existence check).

---

## Tier 2 — Entry / clause types

One structured element inside a list. Each composes Tier-1 atoms.

### Type 4: `Condition` (precondition / postcondition item)

**Source:** `INTERPRETER.md` §"`_preconditions`" (lines 79–93),
§"`_postconditions`" (lines 279–289).

**What it represents:** ONE item in a `_preconditions` or `_postconditions` list.
The grammar does NOT distinguish the item SHAPE between pre and post (only which
list it sits in), so pre and post share ONE type, tagged by `context`. This is
the first Tier-2 type — it COMPOSES two Tier-1 atoms: a `CheckVerb` (the test) +
an optional `ErrorAction` (the failure response).

**Shape:**

```
Condition {
  verb: CheckVerb            # the test (exactly one check-verb)
  onFailure?: ErrorAction    # optional failure response
  context: "pre" | "post"    # which list it came from
}
```

**Parser invariants** (NOT expressible in the shape — enforced at parse / by
checks; the type stays the clean `{verb, onFailure?, context}`):

- A precondition item is a single YAML object with EXACTLY ONE check-verb key
  plus an optional `_on_failure`. Any other key (or >1 verb key) = INVALID.
- `_assert` may appear ONLY when `context == "post"` (post-only; the verb's own
  metadata gates this).
- If `onFailure` is absent AND the verb is not `_assert` -> WARN: only `_assert`
  has a documented default action (halt) when `_on_failure` is omitted
  (INTERPRETER lines 79–80 say "verb PLUS an `_on_failure`"; line 281 carves the
  `_assert` exception).

**`_on_failure` value:** one `ErrorAction`, in block form
(`_on_failure:\n  _halt_and_inform: >`) or inline (`_on_failure: _unrecoverable`).
Both parse to the same `ErrorAction`.

> DECISION (settled): ONE shared `Condition` type with a `context` field (NOT two
> `Precondition`/`Postcondition` types) — the grammar distinguishes only the LIST,
> not the item shape, so a single type is consistent with the "distinct types
> where the grammar distinguishes" principle. `onFailure` is optional on the type,
> with a check flagging its absence on non-`_assert` verbs. "Exactly one verb
> key" is a parser invariant, not a type field.
>
> UN-PARKED (`reason`/`_reason`, from Type 1): a `Condition` item does NOT carry
> `reason` — none of the real precondition items do. `reason` belongs to
> `_re_entry_guard` (a different type, modeled later). The Type-1 parked nuance is
> resolved here for the precondition context: `Condition` owns no `reason`.

**Validation power this unlocks:**

- every condition item composes exactly one valid `CheckVerb` + at most one valid
  `ErrorAction` (closed-set on both halves, via the Tier-1 types);
- `_assert` only in postconditions (context check);
- non-`_assert` verb with no `_on_failure` -> warn (no documented default);
- a STOP on-failure action (`_halt_and_inform`/`_unrecoverable`) MAY carry a
  message; it is optional (bare forms exist) — the Tier-1 shape allows both.

### Type 5: `FragmentRef` (a `_fragments` entry)

**Source:** `INTERPRETER.md` §"`_fragments`" (lines 181–195).

**What it represents:** ONE entry in a phase's ordered `_fragments` list — the
phase's reference to a fragment it composes. "The phase owns triggering, not the
fragment." Composes Tier-1 `Trigger`.

**Shape:**

```
FragmentRef {
  id: str            # _id — fragment name; matches the target file's _fragment
  trigger: Trigger   # _trigger — WHEN it runs (Type 3)
  file: str          # _file — the fragment file path
}
```

All three keys required (no defaults in the spec).

**Parser invariants / cross-reference checks** (NOT shape — enforced in the check
layer; the type stays the clean `{id, trigger, file}`):

- exactly these 3 `_`-keys; any other = INVALID (Golden rule 4).
- `id` matches the `_fragment` key of the unit at `file` (cross-unit reference).
- `file` resolves to an existing fragment unit on disk.

**Behavior, not shape:** `_file` is "loaded ONLY when the trigger is true"
(context economy, lines 194–195) — a runtime interpreter rule tied to the
progressive-disclosure contract, not a property of the entry. `file` is just the
path.

**Ordering:** the `_fragments` list is ORDERED (fragments run in list order). That
ordering is owned by the phase's `fragments: FragmentRef[]` ARRAY (Tier 3), not by
this entry — the entry is order-agnostic.

> DECISION (settled): all three keys required; `id`↔`_fragment` match is a
> cross-reference CHECK (the type holds both halves, a check ties them — like
> `Condition`); the `_assemble` sibling is NOT a `FragmentRef` (it is `{_file}`
> only — no `_id`/`_trigger`, always runs) and is modeled as a separate
> `AssemblerRef` deferred to the phase-frontmatter tier; ordering is the array's
> job.

**Validation power this unlocks:**

- every `_fragments` entry has exactly `{_id, _trigger, _file}` and a valid
  `Trigger` (closed-set on the trigger, via Tier-1);
- each `_id` resolves to a real fragment file whose `_fragment` matches it
  (cross-unit reference integrity);
- no two entries share an `_id` within a phase (a future uniqueness check on the
  array).

### Type 6: `Guarded` (a `_knowledge` / `_templates` entry)

**Source:** `INTERPRETER.md` §"`_knowledge`" (lines 100–114), §"`_templates`"
(~145–155).

**What it represents:** ONE entry in a phase's `_knowledge` OR `_templates` list —
a file reference plus an optional load guard. The phase `_knowledge`/`_templates`
is the SOLE load decision: a file enters context IFF its `_when` guard is true; a
bare `file:` (no `_when`) always loads. Composes Tier-1 `WhenCondition` (the
THIRD `_when` context) — completing the proof that every Tier-1 type composes.

**Shape — ONE type for both lists** (identical shape + identical loading contract;
only the SEMANTIC role differs: knowledge = lookup data CONSUMED to compute;
template = output skeleton EMITTED to disk):

```
Guarded {
  file: str                       # the data/template file path
  when?: WhenCondition            # optional load guard; ABSENT = always loads
  role: "knowledge" | "template"  # which list it came from (enables path/semantic checks)
}
```

**Checks** (NOT shape — the type stays clean `{file, when?, role}`):

- **guard-scope** (THE central check, lines 108–114): `when` may reference ONLY
  the phase's `_input` artifacts — never a fragment output, assemble result, or
  any later-computed value. This is the drift we fixed by hand earlier; the
  shared `WhenCondition` atom makes it ONE check, parameterized by "allowed
  scope," runnable across all three `_when` contexts.
- `file` path resolves on disk AND is declared exactly once (single load owner).
- `role == "knowledge"` -> path under `knowledge/<phase>/`; `role == "template"`
  -> path under `templates/<phase>/`.

**Key/value namespace asymmetry:** `file` is a NON-`_` key (author-namespace per
Golden rule 4), yet its VALUE (the path) is structure-validated (must resolve, must
be the single load owner). The type holds `file: string`; checks validate the value.

> DECISION (settled): ONE `Guarded` type with a `role` field (identical shape for
> `_knowledge`/`_templates`; role enables path/semantic checks) — consistent with
> the `Condition` context-tag decision. Guard-scope is a CHECK over the composed
> `WhenCondition` (the payoff of the shared atom), not shape. `file` is a plain
> string; path-resolution + single-owner are checks. `when?` optional, absent =
> always-load (mirrors `_always`).
>
> DISTINCTION (step-level `_knowledge` is NOT `Guarded`): a `## Step:` `meta`
> `_knowledge: [files]` is a USES annotation — a bare filename list, NO `_when`,
> NEVER loads (lines 116–125). So step `_knowledge` is `string[]`; phase
> `_knowledge` is `Guarded[]`. Same key name, different type by context. `Guarded`
> models ONLY the phase-frontmatter entry; the step uses-annotation is a separate,
> simpler type deferred to the step/meta tier.

**Validation power this unlocks:**

- guard-scope enforced mechanically (the hand-fixed drift becomes a build check);
- single-load-owner (each knowledge/template file declared once across the phase);
- knowledge-vs-template path conventions;
- combined with step `_knowledge` (later): the uses-subset rule (every step file
  ⊆ the phase `Guarded` files).

### Type 7: `ReEntryGuard` (the `_re_entry_guard` interlock)

**Source:** `INTERPRETER.md` §"`_re_entry_guard`" (lines 297–337).

**What it represents:** a top-level phase key (a SINGLE object, not a list entry)
— a fail-closed interlock evaluated before `_preconditions`. Re-running a phase
whose outputs already drove downstream phases would silently invalidate that
work; this is the interlock that stops it. Composes Tier-1 `ErrorAction`; reuses
`WhenCondition` for `if`. **Resolves the Type-1 parked `reason` nuance.**

**Shape:**

```
ReEntryGuard {
  if: WhenCondition          # true when a downstream artifact exists / later phase completed
  action: ErrorAction        # performed when `if` true; normally _halt_and_inform (STOP)
  reason: str                # surfaced with the action; maps to the diagnostic reason= field
  onConfirm?: str | str[]    # named reset OR inline downstream-artifact list;
                             #   ABSENT = canonical cascade from the phase chain  [SPEC-FUZZY]
}
```

**Semantics:** if `if` true -> perform `action` with `reason`, STOP, destroy
NOTHING. ONLY on explicit user confirmation -> perform `on_confirm` (reset
downstream phases to pending + remove their `_produces`), then run normally. If
`if` false -> no-op.

**Checks** (NOT shape):

- `action.control == "STOP"` (via `ERROR_ACTION_SEMANTICS`) — else WARN: a CONTINUE
  action (`_warn_and_skip` etc.) defeats a fail-closed interlock. (Payoff of the
  Tier-1 semantics table.)
- guard-scope for `if`: references downstream artifacts / phase-status — the
  INVERSE of a `_knowledge` guard (which references only `_input`). Same shared
  `WhenCondition` atom, different allowed-scope parameter.

> RESOLVED (Type-1 parked `reason`/`_reason`): `reason` (no underscore) is a
> plain-string DIAGNOSTIC field carried by guard/failure contexts — it populates
> the diagnostic `reason=` field (line 367). It is NOT part of `ErrorAction`
> (distinct from `_halt_and_inform`'s `message`) and NOT the step-prose `_reason`
> (which 2b dropped — the step body IS the reason). Three distinct things, now
> separated: `ErrorAction.message` (the surfaced text), guard `reason` (the
> diagnostic field), step prose (the instruction).
>
> DECISION (settled): `reason: string` field; `if` reuses `WhenCondition`
> (inverse scope vs `_knowledge`, scope-is-a-check); `onConfirm?: string |
> string[]` modeled permissively and FLAGGED spec-fuzzy; `action: ErrorAction`
> (any) + a check warns non-STOP actions.
>
> INCONSISTENCY (grammar wart): `_re_entry_guard`'s sub-keys are BARE
> (`if`, `action`, `reason`, `on_confirm`) — no underscore — unlike `_fragments`
> entries whose sub-keys ARE underscored (`_id`, `_trigger`, `_file`). The sub-key
> underscore convention is NOT uniform across the grammar. Recorded; does not
> change the type.
>
> NUANCE (`on_confirm` spec-fuzzy): the spec describes BOTH a "named reset" and an
> "inline downstream-artifact list" (discover spells its list inline until the
> full phase chain is authored), with a canonical-cascade fallback when omitted.
> This duality is not crisply typed in the prose; modeled as `string | string[]`
> for now — a candidate for spec tightening later.

**Validation power this unlocks:**

- a re-entry guard's `action` is a STOP action (interlock integrity);
- `if` references only evaluable downstream/status scope;
- `onConfirm` inline artifact lists match the phase chain's downstream `_produces`
  (a future cross-phase check once the chain is typed).

---

## Tier 3 — Sub-document types

A meaningful SECTION of a file. Composes Tier-2 entries.

### Type 8: `Meta` (a step's machine contract, FORM 2b)

**Source:** `INTERPRETER.md` §"`_steps`" (lines 228–250), CORRECTED against the
REAL meta-block vocabulary observed across all phase files (the spec's prose
`_steps` list and reality diverge — see the SPEC-GAP note).

**What it represents:** the fenced `` ```meta ``` `` block directly under a
`## Step: <id>` heading — the step's machine contract. In FORM 2b, `_id` is the
heading and `_reason` IS the prose body, so neither is in `Meta`; `Meta` covers
only the machine-contract keys.

**Shape — FLAT (no recursion).** Evidence-confirmed: in FORM 2b there is NO
`_cases` key — `_branch_on` names the discriminant field and the CASE BODIES ARE
PROSE. The meta block is a flat set of optional keys:

```
Meta {
  # uses-annotations (string[], NOT Guarded — never load)
  knowledge?: string[]     # _knowledge  — DATA files this step uses
  templates?: string[]     # _templates  — template files this step uses (parallels _knowledge)
  # iteration / branching
  forEach?: string         # _for_each   — collection to iterate, input order
  branchOn?: string        # _branch_on  — discriminant field; case bodies are PROSE (no _cases in 2b)
  collect?: string[]       # _collect    — accumulator lists appended across iteration
  # outputs
  writes?: string|string[] # _writes     — artifact(s) written to $MIGRATION_DIR/ (file or list)
  writesVar?: string       # _writes_var — in-run STATE later steps reference
  # assembler-step IO (assembler steps only)
  reads?: string[]         # _reads      — files this step reads
  mutates?: string[]       # _mutates    — files this step mutates in place
  # gate
  when?: WhenCondition     # _when       — run step ONLY if true (the FOURTH _when context)
}
```

All fields optional — a step may have an empty meta block (pure-prose step).

> SPEC-GAP (the audit working): INTERPRETER's prose `_steps` section lists
> `_id, _reason, _knowledge, _for_each, _branch_on, _cases, _collect, _writes_var,
> _writes, _when`. The REAL meta blocks across all phases use 10 keys including
> `_templates`, `_reads`, `_mutates` (NOT in the prose list) and NEVER use
> `_cases` (FORM-1-only). So the spec under-lists by 3 and over-lists by 1. Types
> modeled from EVIDENCE; candidate spec fix later: update the `_steps` section to
> list `_templates`/`_reads`/`_mutates` and mark `_cases`/`_default`/`_steps` as
> FORM-1-only.
>
> DECISION (settled): `Meta` models the 10 real FORM-2b keys; `_knowledge` AND
> `_templates` are `string[]` uses-annotations at step level (dual nature vs the
> phase-level `Guarded[]`); `_reads`/`_mutates` are step-meta fields (assembler
> steps), "only-on-assembler" being a check; `_cases`/`_default`/`_steps` are NOT
> modeled — a 2b leak is INVALID; `branchOn` is a flat field (case bodies are
> prose, no recursion); all fields optional.
>
> NUANCE (`_when` fourth context): step-level `_when` reuses `WhenCondition` — the
> FOURTH context (trigger, knowledge-guard, re-entry `if`, step-gate). Scope here =
> phase inputs + in-run state. The shared atom now serves four contexts.
>
> NUANCE (`_writes` is list-or-scalar): evidence (`generate-docs.md`:
> `_writes: [MIGRATION_GUIDE.md, README.md]`) shows a step may write MULTIPLE
> artifacts. The original model had `_writes: string` (too narrow — same class as
> the Type-1 `_unrecoverable` error, caught when bindUnit ran on the real file);
> corrected to `string | string[]`. The binder normalizes a scalar to a
> one-element list.

**Validation power this unlocks:**

- uses-subset: every step `knowledge`/`templates` file ⊆ the phase's `Guarded`
  files (single-load-owner — the long-promised cross-tier check);
- a FORM-1 key (`_cases`/`_default`/`_steps`) in a 2b meta block = INVALID;
- `_reads`/`_mutates` appear only on assembler-unit steps (cross-tier check);
- `_writes_var` names are referenced by some later step (in-run state integrity);
- `branchOn` present implies an iteration/selection context (interaction check).

### Type 9: `Step` (a `## Step:` section, FORM 2b)

**Source:** `INTERPRETER.md` §"FORM 2b" (lines 415–420), §"Unit file regions"
(395–425), §"`_steps`" (`_id`/`_reason`), §"`[_uses:]` prose marker" (127–145).

**What it represents:** ONE `## Step: <id>` section — the unit's executable
procedure unit. Composes `Meta` (Type #8). In FORM 2b a step is: the heading id,
an OPTIONAL `` ```meta ``` `` block, then reason prose ("the body prose IS the
reason" — authoritative for HOW, Golden rule 3).

**Shape — with a structured `uses` projection:**

````
Step {
  id: str          # from `## Step: <id>` heading
  meta?: Meta      # optional ```meta``` block (Type 8)
  prose: str       # the human instruction, verbatim (the _reason)
  uses: str[]      # the [_uses: F] markers EXTRACTED from prose — the checkable
                   #   projection binding prose file-refs back to meta
}
````

`uses` is a DERIVED field (parsed out of `prose`) — unlike most types which mirror
raw structure. It is carried on `Step` deliberately so the `[_uses:]`↔meta binding
is a first-class STRUCTURAL check (the whole reason the marker exists) rather than
a regex buried in the check layer. `prose` remains the verbatim instruction.

**Checks** (NOT shape):

- `id` unique within the unit (array-level, Tier 4).
- every `uses[]` entry ∈ `meta.knowledge ∪ meta.templates` (THE binding check).
- every structure-owned backtick file-ref in `prose` IS tagged `[_uses:]`
  (the untagged-drift check; filenames that are the step's own `_writes`/
  `_produces` output, or inside fenced code, are exempt).

> DECISION (settled): `meta?` optional, `prose` required; `id` uniqueness is a
> unit-level check (`Step.id` a plain string); modeled with the STRUCTURED `uses`
> projection (option b) — makes the marker-to-meta binding a first-class type
> field. `Step` is strictly the `## Step:` section; Orientation and the H1 are
> sibling sub-document concerns (separate types/fields).

**Validation power this unlocks:**

- the `[_uses: F]`↔`meta` binding becomes a structural field check, not a regex;
- combined with `Meta` uses-subset + phase `Guarded`: the full chain
  prose-ref -> step-meta -> phase-load-owner is checkable end to end;
- untagged structure-owned refs in prose are flagged (drift surface closed).

### Type 10: `Orientation` (the `## Orientation` section)

**Source:** `INTERPRETER.md` §"Unit file regions" (lines 401–414), Golden rule 6.

**What it represents:** the single optional `## Orientation` section, immediately
after the H1. NON-NORMATIVE: the interpreter READS it for context but MUST NOT
execute it; it carries NO binding instruction (every rule lives in the
frontmatter or a `## Step:`). A unit MAY omit it; if present, exactly one, and
only here.

**Shape — minimal:**

```
Orientation {
  prose: str    # the non-normative orienting text (verbatim)
}
```

No composition — it is pure prose. Carried as its own type (rather than a bare
string on the unit) so the "recap-with-pointer only" check has a clear home and
the unit's `orientation?: Orientation` reads self-documenting.

**Checks** (NOT shape):

- recap-with-pointer ONLY: any contract recap MUST explicitly point at the
  authoritative frontmatter key (e.g. "advances per `_advances_to`"); prose that
  states a RULE as its source (not pointing at the key) is a violation (Golden
  rule 6 — no normative content in Orientation).
- at most ONE `## Orientation`, positioned immediately after the H1 (a regions
  check at the unit level).

> DECISION (settled): modeled as `{ prose: string }` (own type, not a bare string
> on the unit) so the non-normative/recap-pointer check has a home; optional on
> the unit; uniqueness + position are unit-level regions checks.

**Validation power this unlocks:**

- Orientation carries no rule-as-source prose (the non-normative guarantee);
- the regions invariant (≤1 Orientation, right after H1, nothing normative).

---

## Tier 2 (addendum) — sub-types the Frontmatter composites need

Two small entry types deferred earlier, now built because the Tier-3
`Frontmatter` types compose them. (Recorded here in build order; they are
conceptually Tier 2.)

### Type 11: `OnErrorTable` (the `_on_error` documentation block)

**Source:** `INTERPRETER.md` §"`_on_error`" (lines 158–165), §"ERROR ACTIONS"
(349–365). Resolves the Type-1 deferred "documentation table" sibling.

**What it represents:** the phase/unit `_on_error:` block. NOT a carrier of one
`ErrorAction` — it is a REFERENCE TABLE mapping the error-action names this unit
uses to their documented `{effect, status}`. "It is NOT executed … treat it as
documentation" (line 162). The canonical ERROR ACTIONS section is authoritative
over it (line 165).

**Shape:**

```
OnErrorTable {
  entries: Record<ErrorActionKind, { effect: str, status: str }>
}
```

A partial map — a unit documents only the actions it uses (e.g. discover's table
lists `_warn_and_skip`, `_halt_and_inform`, `_unrecoverable`).

**Checks** (NOT shape):

- every key is a valid `ErrorActionKind` (closed-set, via Tier-1);
- each entry's `{effect, status}` MATCHES the canonical `ERROR_ACTION_SEMANTICS`
  (the drift catch — the table restates the canonical meaning and could drift;
  ERROR ACTIONS is authoritative).

> RESOLVED (Type-1 deferred): `_on_error` is its own documentation-table type,
> distinct from `ErrorAction` (the enum) and from `_on_failure` (which carries
> ONE action). The asymmetry from Type 1 is now fully typed.

### Type 12: `AssemblerRef` (a phase's `_assemble` pointer)

**Source:** `INTERPRETER.md` §"`_assemble`" (phase body). Resolves the Type-5
deferred sibling.

**What it represents:** in the PHASE frontmatter, `_assemble` is a REFERENCE to
the single assembler file — shape `{_file}`. (Distinct from the ASSEMBLER
frontmatter's `_assemble`, which is the assembler's ID string — same key, two
types by context, like `_knowledge`'s dual nature.)

**Shape:**

```
AssemblerRef {
  file: str    # _file — the assembler file path
}
```

Simpler than `FragmentRef` (no `_id`, no `_trigger` — the assembler always runs,
exactly one per phase).

**Checks** (NOT shape):

- `file` resolves to an existing assembler unit on disk;
- that unit's `_of_phase` matches the owning phase (cross-reference).

> RESOLVED (Type-5 deferred): the `_assemble` sibling is `AssemblerRef {file}` —
> NOT a `FragmentRef` (no id/trigger; always runs).

---

## Tier 3 (cont.) — the Frontmatter types

### Type 13: `Frontmatter` (Phase / Fragment / Assembler)

**Source:** `INTERPRETER.md` §"Phase identity" (31–38), §"`_input`" (44–57),
§"`_init`" (59–), §"`_fragments`/`_assemble`" (167–236), §"`_produces`/
`_advances_to`/`_forbids_files`" (339–345).

**What it represents:** the `---`…`---` STRUCTURAL contract block — "the single
source of truth for the unit's contract." The grammar has THREE distinct key-sets
(phase = composer; fragment = unit of work; assembler = combine/enrich, terminal),
so this is THREE types. Fragment and Assembler share a `UnitFrontmatterCore`.

**Shared core (Fragment + Assembler):**

```
UnitFrontmatterCore {
  ofPhase: str              # _of_phase — owning-phase back-reference
  scope: str                # _scope — hard boundary
  produces: str[]           # _produces — files CREATED (fragment: 1..N; assembler: 0..N)
  preconditions?: Condition[]   # _preconditions (optional)
  postconditions: Condition[]   # _postconditions
  onError: OnErrorTable     # _on_error
}
```

**FragmentFrontmatter** = core + `{ fragment: str }` (`_fragment` — id matching
the phase's `_fragments[]._id`).

**AssemblerFrontmatter** = core + `{ assemble: str, reads?: str[], mutates?: str[] }`
(`_assemble` id; `_reads`/`_mutates` 0..N — the only mutator).

**PhaseFrontmatter** (the composer — its own shape):

```
PhaseFrontmatter {
  phase: str                    # _phase — identity (diagnostics)
  title?: str                   # _title — cosmetic
  requiresPhase: str | null     # _requires_phase — upstream gate (null = first phase)
  scope: str                    # _scope
  init?: InitBlock              # _init — FIRST phase only (when requiresPhase == null); SHALLOW [see note]
  reEntryGuard?: ReEntryGuard   # _re_entry_guard
  input: str[]                  # _input — artifacts/globs consumed
  preconditions?: Condition[]   # _preconditions
  knowledge?: Guarded[]         # _knowledge — SOLE load decision
  templates?: Guarded[]         # _templates
  fragments: FragmentRef[]      # _fragments — composition (ordered)
  assemble: AssemblerRef        # _assemble — the single assembler ({_file})
  postconditions?: Condition[]  # _postconditions — cross-cutting
  produces: str[]               # _produces
  advancesTo: str               # _advances_to
  forbidsFiles?: str[]          # _forbids_files
  onError: OnErrorTable         # _on_error
}
```

**Composition payoff:** PhaseFrontmatter composes FIVE earlier types — `ReEntryGuard`,
`Condition[]`, `Guarded[]`, `FragmentRef[]`, `AssemblerRef`, `OnErrorTable`. Every
Tier-1/2 guarantee flows up for free.

> DECISION (settled): three frontmatter types; Fragment+Assembler share
> `UnitFrontmatterCore`; `_on_error` -> `OnErrorTable` (Type 11); phase `_assemble`
> -> `AssemblerRef` (Type 12); `_input: string[]` (glob-vs-artifact is a check);
> required/optional applied per spec.
>
> NUANCE (`_init` shallow): `_init` is a first-phase-only block with its own verb
> sub-grammar (`_init_migration_run`, etc.). Modeled SHALLOWLY for now (an opaque
> `InitBlock` marker) — a candidate for full verb-union modeling later, like
> `CheckVerb`. Flagged.
>
> NUANCE (`_assemble` dual type, confirmed): phase `_assemble` = `AssemblerRef`;
> assembler-frontmatter `_assemble` = `string` id. Same key, two types by context.

**Validation power this unlocks:**

- `_init` present IFF `requiresPhase == null` (first-phase invariant);
- `_reads`/`_mutates` only on Assembler (the only-mutator rule);
- phase `_produces` == union of fragment `_produces` + assembler `_produces`/
  `_mutates` (the ownership identity, INTERPRETER lines 222–224 — a cross-unit check);
- every `_of_phase` matches the owning phase; every `_fragment` id resolves;
- closed-vocabulary: any `_`-key not in the type's key-set = INVALID.

---

## Tier 4 — Unit types (whole files)

A whole `.md` file. Composes the Tier-3 sections per the "Unit file regions"
grammar (INTERPRETER lines 395–425): every unit is EXACTLY, in order:
Frontmatter -> H1 -> optional Orientation -> zero-or-more Steps -> NOTHING else.

### Type 14: `Unit` (Phase / Fragment / Assembler)

**Source:** `INTERPRETER.md` §"Unit file regions" (395–425), Golden rule 6.

**What it represents:** the parsed whole-file — the top-level type a parser
produces from a `.md` file. THREE kinds, matching the three `Frontmatter` kinds.
The kind of the unit MUST equal the kind of its frontmatter (a `PhaseFrontmatter`
yields a `Phase`).

**Shared regions (all three):**

```
UnitRegions {
  title?: str               # the H1 (cosmetic; interpreter assigns no meaning)
  orientation?: Orientation # the optional ## Orientation section
  steps: Step[]             # zero-or-more ## Step: sections, in order
}
```

**The three units:**

```
Phase     { kind: "phase";     frontmatter: PhaseFrontmatter;     ...UnitRegions }  # steps MUST be empty
Fragment  { kind: "fragment";  frontmatter: FragmentFrontmatter;  ...UnitRegions }  # steps MUST be non-empty
Assembler { kind: "assembler"; frontmatter: AssemblerFrontmatter; ...UnitRegions }  # steps MUST be non-empty

Unit = Phase | Fragment | Assembler   # discriminated on kind
```

**Composition payoff (the apex):** a `Phase` transitively composes EVERY type —
`PhaseFrontmatter` -> {`ReEntryGuard`, `Condition[]`, `Guarded[]`, `FragmentRef[]`
(-> `Trigger`), `AssemblerRef`, `OnErrorTable` (-> `ErrorAction`)} and the body
-> `Step[]` -> `Meta` -> `WhenCondition`. The whole type system meets here; every
Tier-1 guarantee holds at the top for free.

**Region invariants** (checks, not shape — the regions grammar):

- steps EMPTY for a phase; NON-EMPTY for a fragment/assembler (lines 417–420);
- at most ONE `## Orientation`, immediately after the H1;
- NOTHING after the last step (no trailing `## Output`/`## Scope`/`## Notes` —
  forbidden duplication, Golden rule 6);
- `unit.kind == unit.frontmatter.kind` (the kind-match invariant).

> DECISION (settled): three `Unit` kinds discriminated on `kind`, each carrying
> its matching `Frontmatter` + shared `UnitRegions` (title?/orientation?/steps).
> The phase-zero-steps vs fragment/assembler-nonempty-steps rule is a CHECK
> (the shape allows `steps: Step[]` for all; the invariant constrains it) — a
> phase with steps, or a fragment with none, is INVALID.

**Validation power this unlocks (the whole-file level):**

- the complete regions grammar (order, the no-trailing-prose rule, orientation
  position/count);
- phase-has-no-steps / unit-has-steps;
- kind consistency between unit and frontmatter;
- and, transitively, EVERY check from every tier below, because a `Unit` contains
  the entire typed graph.

---

## The parser (text -> typed `Unit`)

The types say WHAT shape is valid; the parser EXTRACTS that shape from a `.md`
file. Two layers, kept separate (one job each):

1. **YAML-subset reader** (`text -> YamlValue`) — pure SYNTAX. Knows nothing
   about the DSL; parses the constrained subset below into a plain value tree
   (map / array / string / bool / null).
2. **DSL binders** (`YamlValue -> ErrorAction | Condition | … | Unit`) — pure
   DSL SEMANTICS. Built bottom-up, mirroring the type tiers (one binder per type).

### The YAML subset (catalogued from the real frontmatter — evidence-based)

The DSL frontmatter uses ONLY these constructs. Anything outside this subset is a
parse error (and almost certainly not valid DSL anyway).

- **Comments:** full-line `# …` (skip). (No trailing inline comments observed.)
- **Scalar `key: value`** — bare token (`_phase: design`), quoted string
  (`_title: "…"`), `null`, `true`/`false`.
- **Folded block scalar** `key: >` + indented continuation. (Literal `|` NOT
  used — only `>`.)
- **Block sequence:** `key:` then `- item` lines (items may be scalars, inline
  maps, or `key: value` map-entries forming a map).
- **Block (nested) map:** `key:` then indented `subkey: value` lines.
- **Flow map:** inline `{ a: x, b: y }`, including NESTED (`{ k: { … } }`).
- **Flow sequence:** inline `[a, b, c]` and empty `[]`.

NOT in the subset (parse-error if seen): anchors/aliases, tags, multi-doc `---`
within frontmatter, flow scalars with special types, complex keys.

### `YamlValue`

```
YamlValue = string | boolean | null | YamlValue[] | { [k: string]: YamlValue }
```

Numbers are kept as STRINGS at the YAML layer (the DSL has no bare numeric YAML
values in frontmatter; numerics live inside JSON knowledge files, parsed by
`JSON.parse` separately). Binders coerce where a type needs it.

> DECISION (settled): hand-written minimal YAML-subset reader (ZERO npm deps to
> run — preserves the architecture property); parser-first so every check runs on
> real parsed phase files; two layers (syntax reader + DSL binders) so each has
> one job; binders built bottom-up like the types.

## The check layer + orchestrator (COMPLETE)

Checks consume typed `Unit`s (the binders already validated shape +
closed-vocabulary) and emit `Finding`s for the SEMANTIC / CROSS-REFERENCE rules.

**Intra-unit** (`checks/`): `regions` (phase=0 steps, frag/asm≥1), `uses`
(`[_uses:F]` ∈ step meta), `assert-post-only`, `interlock` (re-entry action is
STOP, via `ERROR_ACTION_SEMANTICS`).

**Cross-unit**: `fragment-ref` (refs resolve: file/kind/`_of_phase`/id),
`subset` (step files ⊆ owning-phase `Guarded` — single-load-owner), `guard-scope`
(a `_when` guard naming a produced-not-input artifact — warning), `produces`
(phase `_produces` == union of fragment/assembler produces+mutates, EXEMPTING
assembler-`_reads` intermediates + directory-prefix coverage), `phase-chain`
(`_advances_to`/`_requires_phase` consistency), `xtable` (producer-emits ∈
consumer-keys — the RDS-gap catcher, ported from the Python validator).

**Orchestrator + CLI** (`validate.ts`): discover unit files -> `bindUnit` each
(collecting bind-time findings) -> run all checks -> report -> exit non-zero on
any error (`--strict` also fails on warnings). Runs as
`node scripts/dsl-validator/validate.ts <root>`; reports `22 unit files / OK`.

> EVIDENCE CORRECTION (`produces`): the literal ownership-identity rule
> (INTERPRETER 222–224) was too strict — it flagged `billing-profile.json` /
> `_eks-design.json` (assembler-`_reads` INTERMEDIATES, fragment->assembler
> handoffs, often `_`-prefixed) and `terraform/eks.tf` (covered by the `terraform/`
> DIRECTORY in `_produces`). Refined: exempt assembler-read intermediates; honor
> directory-prefix coverage. The check layer caught this against the real DSL —
> the third evidence-driven correction (after `_unrecoverable` and `_writes`).
>
> MIGRATION: `lint:dsl` in `mise.toml` now runs the TS validator
> (`validate.ts`) instead of the Python `scripts/validate_dsl.py`; `npm:typescript`
> added + a `lint:types` (`tsc --noEmit`) gate wired into `lint`. `mise.toml` is
> admin-owned (`@awslabs/startups-admins`) — flagged. The Python `validate_dsl.py`
> is SUPERSEDED (kept for now; retire in a follow-up).
