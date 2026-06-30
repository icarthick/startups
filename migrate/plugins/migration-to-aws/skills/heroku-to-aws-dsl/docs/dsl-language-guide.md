# The DSL Language — A Four-Tier Guide

A companion to `dsl-types.md`. Where `dsl-types.md` is the canonical model (every
nuance, every parked decision, the drift contract), THIS document is the
**teaching walk-through**: it explains the DSL as a *language* built in four
tiers, and for each construct shows three things side by side —

1. **The grammar** — what the `_`-key looks like in a `.md` unit file.
2. **The TypeScript type** — the shape the binder produces (verbatim from
   `scripts/dsl-validator/types/`).
3. **The binding** — a real snippet of markdown from the skill, and what it
   becomes when parsed.

> **How to read this.** The DSL is a closed `_`-prefixed vocabulary that an LLM
> interprets at runtime. There is NO engine — the markdown IS the program, the
> LLM IS the interpreter, and the TypeScript validator is a *compile-time*
> conformance checker that never runs at plugin time. The four tiers are how we
> made an LLM-interpreted markdown dialect **statically checkable**: model the
> grammar as types, parse real files into those types, then check the rules the
> types can't express.

---

## Why four tiers?

The grammar has a natural dependency order: a whole file is built from
sections, a section from list-entries, a list-entry from atomic values. You cannot
understand a `Phase` until you understand a `FragmentRef`; you cannot understand
a `FragmentRef` until you understand a `Trigger`. So the type system is defined
**bottom-up** and each tier composes only the tiers below it.

| Tier | Category | What it is | Examples |
| ---- | -------- | ---------- | -------- |
| **1** | **Value types** | closed sets / atoms; depend on nothing | `ErrorAction`, `Trigger`, `CheckVerb`, `WhenCondition` |
| **2** | **Entry / clause types** | one structured element inside a list | `Condition`, `Guarded`, `FragmentRef`, `ReEntryGuard` |
| **3** | **Sub-document types** | a meaningful section of a file | `Meta`, `Step`, `Orientation`, `Frontmatter` |
| **4** | **Unit types** | a whole file | `Phase`, `Fragment`, `Assembler` |

The payoff of bottom-up composition: every guarantee proven at Tier 1 flows up
for free. When `Phase` (Tier 4) contains a `FragmentRef` (Tier 2) that contains a
`Trigger` (Tier 1), the "a trigger is exactly one of five closed forms" guarantee
is already true by the time you reach the phase. The apex type `Phase`
transitively composes **every** type in the system — validate a `Phase` and you
have validated the whole graph.

### The two design rules that hold across all tiers

1. **The `kind` discriminant IS the raw DSL token.** `ErrorAction.kind` is
   literally `"_halt_and_inform"`, `Trigger.kind` is literally `"_glob"`. The
   type mirrors the grammar with no translation layer — the parser reads a YAML
   key and that key *is* the discriminant. This is why a typo'd `_`-key fails
   loudly (Golden Rule 4 / `CLOSED_VOCAB`): it matches no variant.

2. **Types are PURE shape; rules are CHECKS.** A type says *what shape is valid*.
   It never carries a rule like "guards may reference only `_input`" or "`_assert`
   is post-only." Those are **checks** in `scripts/dsl-validator/checks/`, run
   over the bound types. Keeping shape and rule separate is why one parse pass can
   collect many findings instead of throwing at the first.

---

## Tier 1 — Value types (the atoms)

Closed sets and atomic values that depend on nothing. Each is a discriminated
union on a `kind` token (except the single-field `WhenCondition`). Each ships a
`*_KINDS` array — the **one** place the closed vocabulary lives, read by both the
parser and the closed-vocab check, so there is no drift.

---

### 1.1 `WhenCondition` — the shared plain-language atom

The simplest type, and the most reused. `_when` appears in **four** contexts (a
fragment trigger, a step gate, a `_knowledge` load guard, and the re-entry `if`).
All four are structurally the same thing — a plain-language condition the LLM
evaluates — so they share one atom. What *differs* per context is the SCOPE the
condition may reference, and that is a check (`guard-scope`), not a shape.

**The TypeScript type** (`types/when-condition.ts`):

```ts
export interface WhenCondition {
  /** The plain-language condition string, evaluated by the LLM at runtime. */
  readonly condition: string;
}
```

**The grammar + binding.** Anywhere you see a `_when:`, its value becomes a
`WhenCondition`. From `discover.phase.md`'s re-entry guard:

```yaml
_re_entry_guard:
  if: "preferences.json exists AND phase clarify completed"
```

The string `"preferences.json exists AND phase clarify completed"` binds to:

```ts
{ condition: "preferences.json exists AND phase clarify completed" }
```

That's it — no parsing of the English. The LLM reads it at runtime; the validator
only checks (elsewhere) that the *scope* it references is evaluable.

---

### 1.2 `ErrorAction` — the closed set of 5 failure responses

What to do when a check or operation fails. A tagged union on `kind`. The two
STOP variants carry an **optional** surfaced message; the three CONTINUE variants
are nullary (they never surface text).

**The TypeScript type** (`types/error-action.ts`, abridged):

```ts
export interface HaltAndInform { readonly kind: "_halt_and_inform"; readonly message?: string; }
export interface WarnAndSkip    { readonly kind: "_warn_and_skip"; }
export interface Defer          { readonly kind: "_defer"; }
export interface DefaultAndWarn { readonly kind: "_default_and_warn"; }
export interface Unrecoverable  { readonly kind: "_unrecoverable"; readonly message?: string; }

export type ErrorAction =
  | HaltAndInform | WarnAndSkip | Defer | DefaultAndWarn | Unrecoverable;
```

The static semantics (control flow + status transition) live in a separate lookup
table, NOT on the variants, so checks can reason about an action without
re-reading prose:

```ts
export const ERROR_ACTION_SEMANTICS = {
  _halt_and_inform: { control: "STOP",     statusEffect: "retain_in_progress", sideEffect: "..." },
  _warn_and_skip:   { control: "CONTINUE", statusEffect: null,                 sideEffect: "..." },
  _unrecoverable:   { control: "STOP",     statusEffect: "revert_pending",     sideEffect: "..." },
  // ...
};
```

**The grammar + binding — two forms.** An action appears either as a bare token
or as a key carrying a message. From `discover.phase.md`:

```yaml
# bare form — nullary, or a STOP action that omits its message
_on_failure: _unrecoverable

# message form — a STOP action surfacing text (folded block scalar)
_on_failure:
  _halt_and_inform: >
    Another core phase is already in_progress. At most one phase may be
    active at a time. Resolve the active phase before re-running discover.
```

These bind, respectively, to:

```ts
{ kind: "_unrecoverable" }                                   // message omitted (optional)
{ kind: "_halt_and_inform", message: "Another core phase…" } // message present
```

> **Why this shape was non-obvious.** The original model put `message` only on
> `_halt_and_inform`. Building the type from *real files* disproved it:
> `_unrecoverable` also carries a block-scalar message in some `_on_failure`
> carriers, AND both STOP actions also appear bare. So `message` is optional on
> *both* STOP variants. `tsc` caught the original error when a probe built an
> `_unrecoverable` with a message — the type system validating its own model.

---

### 1.3 `CheckVerb` — the closed set of 7 check verbs

The test half of a precondition/postcondition (the failure-response half is
`ErrorAction`). A tagged union; the verbs have **heterogeneous** argument shapes,
so each variant carries its own argument type.

**The TypeScript type** (`types/check-verb.ts`, abridged):

```ts
export interface SourceExistsArg { readonly glob: string; readonly containing?: string; }

export interface CheckPhaseCompleted   { readonly kind: "_check_phase_completed"; readonly phase: string; }
export interface CheckSingleActivePhase{ readonly kind: "_check_single_active_phase"; }   // nullary
export interface CheckFileExists       { readonly kind: "_check_file_exists"; readonly paths: string | readonly string[]; }
export interface ValidateJson          { readonly kind: "_validate_json"; readonly paths: string | readonly string[]; }
export interface ValidateSchema        { readonly kind: "_validate_schema"; readonly file: string; readonly schema: string; }
export interface CheckSourceExists     { readonly kind: "_check_source_exists"; readonly arg: SourceExistsArg; }
export interface Assert                { readonly kind: "_assert"; readonly condition: string; }  // POST-ONLY

export type CheckVerb =
  | CheckPhaseCompleted | CheckSingleActivePhase | CheckFileExists
  | ValidateJson | ValidateSchema | CheckSourceExists | Assert;
```

Each verb's *context* (may it appear in pre-, post-, or both lists?) lives in a
metadata table, so "`_assert` is post-only" is data-driven, not hard-coded:

```ts
export const CHECK_VERB_META = {
  _assert: { context: "post", defaultOnFailure: "halt_gate_fail" },
  // every other verb: { context: "both" }
};
```

**The grammar + binding.** The YAML key is the verb token; its value is the
argument. From `design-assemble.md`:

```yaml
_postconditions:
  - _validate_json: aws-design.json
  - _validate_schema: { file: aws-design.json, schema: schemas/aws-design.schema.json }
  - _assert: "metadata.total_services == services[].length"
```

binds to three `CheckVerb`s:

```ts
{ kind: "_validate_json",   paths: "aws-design.json" }
{ kind: "_validate_schema", file: "aws-design.json", schema: "schemas/aws-design.schema.json" }
{ kind: "_assert",          condition: "metadata.total_services == services[].length" }
```

> Note `SourceExistsArg` is defined here but **shared** with the `Trigger` tier —
> `_check_source_exists` is both a check verb and a trigger form, same
> `{glob, containing?}` shape.

---

### 1.4 `Trigger` — the closed set of 5 "when does a fragment run" forms

WHEN a fragment fires. "The phase owns triggering, not the fragment." Exactly one
of five forms; a false trigger simply skips the fragment.

**The TypeScript type** (`types/trigger.ts`, abridged):

```ts
export interface AlwaysTrigger            { readonly kind: "_always"; }                                  // nullary
export interface GlobTrigger              { readonly kind: "_glob"; readonly patterns: string | readonly string[]; }
export interface ArtifactExistsTrigger    { readonly kind: "_artifact_exists"; readonly names: string | readonly string[]; }
export interface CheckSourceExistsTrigger { readonly kind: "_check_source_exists"; readonly arg: SourceExistsArg; }
export interface WhenTrigger              { readonly kind: "_when"; readonly when: WhenCondition; }

export type Trigger =
  | AlwaysTrigger | GlobTrigger | ArtifactExistsTrigger | CheckSourceExistsTrigger | WhenTrigger;
```

`_glob` and `_artifact_exists` share an argument *shape* (`string | string[]`) but
mean different things — `_glob` matches workspace SOURCE files, `_artifact_exists`
matches RUN artifacts in `$MIGRATION_DIR/`. The `kind` discriminant is exactly
what tells them apart. `WhenTrigger` reuses the Tier-1 `WhenCondition` (its second
of four contexts).

**The grammar + binding.** From `discover.phase.md`'s `_fragments`:

```yaml
_fragments:
  - _id: terraform
    _trigger: { _check_source_exists: { glob: "**/*.tf", containing: 'resource "heroku_' } }
    _file: phases/discover/discover-terraform.md
  - _id: billing
    _trigger: { _glob: ["**/*billing*.{csv,json}", "**/*invoice*.{csv,json}"] }
    _file: phases/discover/discover-billing.md
```

The two `_trigger:` values bind to:

```ts
{ kind: "_check_source_exists", arg: { glob: "**/*.tf", containing: 'resource "heroku_' } }
{ kind: "_glob", patterns: ["**/*billing*.{csv,json}", "**/*invoice*.{csv,json}"] }
```

---

## Tier 2 — Entry / clause types (one element of a list)

Each composes Tier-1 atoms into one structured list-element. This is where the
"composition for free" property first shows: a `Condition` *contains* a
`CheckVerb` and an `ErrorAction`, so both closed-set guarantees already hold.

---

### 2.1 `Condition` — one precondition / postcondition item

The grammar does NOT distinguish the *shape* of a pre- vs post-condition (only
which list it sits in), so they share one type tagged by `context`. It composes
two Tier-1 atoms.

**The TypeScript type** (`types/condition.ts`):

```ts
export type ConditionContext = "pre" | "post";

export interface Condition {
  readonly verb: CheckVerb;          // the test (exactly one verb — a parser invariant)
  readonly onFailure?: ErrorAction;  // optional; only _assert has a documented default (halt)
  readonly context: ConditionContext;
}
```

**The grammar + binding.** A condition item is a YAML object with exactly one
check-verb key plus an optional `_on_failure`. From `discover.phase.md`'s
`_preconditions`:

```yaml
_preconditions:
  - _check_source_exists: { glob: "**/*.tf", containing: 'resource "heroku_' }
    _on_failure:
      _unrecoverable: >
        No Terraform files with heroku_* resources found. Heroku Terraform is
        required for discovery; Procfile/app.json alone are not sufficient.
```

binds to one `Condition`:

```ts
{
  context: "pre",
  verb: { kind: "_check_source_exists", arg: { glob: "**/*.tf", containing: 'resource "heroku_' } },
  onFailure: { kind: "_unrecoverable", message: "No Terraform files with heroku_* resources found. …" },
}
```

A bare `_assert` (no `_on_failure`) is legal — it has a documented default
(GATE_FAIL + halt). A non-`_assert` verb with no `_on_failure` earns a warning.

---

### 2.2 `Guarded` — one `_knowledge` / `_templates` entry

A file reference plus an optional load guard. The phase's `_knowledge`/
`_templates` is the **sole load decision**: a file enters context IFF its `_when`
is true; a bare `file:` always loads. One type serves both lists; only the
semantic `role` differs (knowledge = lookup data consumed; template = skeleton
emitted). Composes `WhenCondition` (its third context).

**The TypeScript type** (`types/guarded.ts`):

```ts
export type GuardedRole = "knowledge" | "template";

export interface Guarded {
  readonly file: string;        // author-namespace key; its VALUE is structure-validated
  readonly when?: WhenCondition; // ABSENT = always loads
  readonly role: GuardedRole;
}
```

**The grammar + binding.** A bare-`file` knowledge entry (always loads). The
design phase loads its tunable-constants sheet unconditionally:

```yaml
_knowledge:
  - file: knowledge/design/design-defaults.json
  - file: knowledge/design/dyno-fargate-sizing.json
```

binds to:

```ts
{ file: "knowledge/design/design-defaults.json",   role: "knowledge" }  // when omitted → always loads
{ file: "knowledge/design/dyno-fargate-sizing.json", role: "knowledge" }
```

A guarded entry (`{file, _when}`) would carry a `when: { condition: "…" }`,
loading only when the predicate over `_input` holds.

> **Same key, two types.** `_knowledge` in a *phase frontmatter* is `Guarded[]`
> (a load decision). `_knowledge` in a *step's* `meta` block is `string[]` — a
> bare uses-annotation that never loads (see Tier 3 `Meta`). The grammar reuses
> the key name; the binder produces a different type per context.

---

### 2.3 `FragmentRef` — one entry in a phase's `_fragments` list

The phase's reference to a fragment it composes. Composes the Tier-1 `Trigger`.
All three keys are required.

**The TypeScript type** (`types/fragment-ref.ts`):

```ts
export interface FragmentRef {
  readonly id: string;       // _id — matches the target file's _fragment (cross-ref check)
  readonly trigger: Trigger; // _trigger — WHEN it runs
  readonly file: string;     // _file — the fragment file path
}
```

**The grammar + binding.** From `discover.phase.md` (same block as 1.4):

```yaml
- _id: terraform
  _trigger: { _check_source_exists: { glob: "**/*.tf", containing: 'resource "heroku_' } }
  _file: phases/discover/discover-terraform.md
```

binds to:

```ts
{
  id: "terraform",
  trigger: { kind: "_check_source_exists", arg: { glob: "**/*.tf", containing: 'resource "heroku_' } },
  file: "phases/discover/discover-terraform.md",
}
```

The `_assemble` sibling is NOT a `FragmentRef` — it has no `_id`/`_trigger` (the
assembler always runs, exactly one per phase), so it is the simpler
`AssemblerRef { file: string }`.

---

### 2.4 `ReEntryGuard` — the fail-closed re-run interlock

A single top-level phase object (not a list entry), evaluated before
preconditions. It stops a phase re-run from silently invalidating downstream work.
Composes `ErrorAction` (the `action`) and reuses `WhenCondition` (the `if`).

**The TypeScript type** (`types/re-entry-guard.ts`):

```ts
export interface ReEntryGuard {
  readonly if: WhenCondition;                  // true when a downstream artifact exists
  readonly action: ErrorAction;                // performed when `if` is true; normally a STOP action
  readonly reason: string;                     // surfaced; maps to the diagnostic reason= field
  readonly onConfirm?: string | readonly string[]; // the reset, ONLY on explicit user confirmation
}
```

**The grammar + binding.** From `discover.phase.md`:

```yaml
_re_entry_guard:
  if: "preferences.json exists AND phase clarify completed"
  action: _halt_and_inform
  reason: stale_downstream
  on_confirm: >
    Reset phases clarify, design, estimate, generate, feedback to "pending" …
```

binds to:

```ts
{
  if: { condition: "preferences.json exists AND phase clarify completed" },
  action: { kind: "_halt_and_inform" },   // bare — no message here
  reason: "stale_downstream",
  onConfirm: "Reset phases clarify, design, estimate, generate, feedback to \"pending\" …",
}
```

> Note the grammar wart this type records: `_re_entry_guard`'s sub-keys are BARE
> (`if`, `action`, `reason`, `on_confirm`) while `_fragments` entries use
> underscored sub-keys (`_id`, `_trigger`, `_file`). The underscore convention is
> not uniform; the type absorbs it but the inconsistency is documented.
>
> Two more Tier-2 helpers complete the set: `OnErrorTable` (the `_on_error:`
> documentation block — a partial map from action name to its `{effect, status}`,
> NOT an executed action) and `AssemblerRef` (the `{file}` pointer above). Both
> exist because the Tier-3 `Frontmatter` composites need them.

---

## Tier 3 — Sub-document types (a section of a file)

Each composes Tier-2 entries into a meaningful file *section*. This is where the
FORM-2b body grammar (the `## Step:` markdown convention) meets the frontmatter
contract.

---

### 3.1 `Meta` — a step's machine contract (the ```` ```meta ```` block)

The fenced block directly under a `## Step:` heading. In FORM 2b, the step `_id`
IS the heading and the `_reason` IS the prose body, so neither is in `Meta` —
`Meta` covers only the machine-contract keys. It is **flat** (no recursion): there
is no `_cases` key in 2b; `_branch_on` names a discriminant and the case bodies
are PROSE.

**The TypeScript type** (`types/meta.ts`, abridged):

```ts
export interface Meta {
  // uses-annotations (string[], NOT Guarded — never load)
  readonly knowledge?: readonly string[];   // _knowledge
  readonly templates?: readonly string[];   // _templates
  // iteration / branching
  readonly forEach?: string;                 // _for_each
  readonly branchOn?: string;                // _branch_on (case bodies are prose)
  readonly branchCases?: readonly string[];  // _branch_cases (discriminant VALUES the arms cover)
  readonly collect?: readonly string[];      // _collect (accumulators)
  // outputs
  readonly writes?: string | readonly string[]; // _writes (file or list)
  readonly writesVar?: string;               // _writes_var (in-run state)
  // assembler-step IO (assembler units only — a check enforces)
  readonly reads?: readonly string[];        // _reads
  readonly mutates?: readonly string[];      // _mutates
  // gate
  readonly when?: WhenCondition;             // _when (the fourth _when context)
}
```

A closed `META_KEYS` array drives the closed-vocab check, and a
`FORM1_ONLY_META_KEYS` list (`_cases`/`_default`/`_steps`) is what `FORM1_LEAK`
rejects if it leaks into a 2b block.

**The grammar + binding.** From `design-mapping.md`'s `map_resources` step:

````markdown
## Step: map_resources

```meta
_for_each: inventory.resources
_branch_on: resource_type
_branch_cases: [formation, addon, pipeline, space, _default]
_collect: [services, deferred, warnings, spaces]
_knowledge: [knowledge/design/design-defaults.json, knowledge/design/dyno-fargate-sizing.json]
```

Process each resource in `inventory.resources[]` in INPUT ORDER…
````

The `meta` block binds to:

```ts
{
  forEach: "inventory.resources",
  branchOn: "resource_type",
  branchCases: ["formation", "addon", "pipeline", "space", "_default"],
  collect: ["services", "deferred", "warnings", "spaces"],
  knowledge: ["knowledge/design/design-defaults.json", "knowledge/design/dyno-fargate-sizing.json"],
}
```

> Note `knowledge` here is `string[]` (a uses-annotation), NOT `Guarded[]` — the
> step only *uses* files the *phase* decided to load. A check (`SUBSET`) enforces
> that every file a step names is declared by its owning phase.

---

### 3.2 `Step` — one `## Step:` section

The unit's executable procedure unit. Composes `Meta`. In FORM 2b a step is: the
heading id, an optional `meta` block, then reason prose ("the body prose IS the
reason"). It carries a *derived* `uses` field — the `[_uses: F]` markers extracted
from the prose, so the marker-to-meta binding is a first-class structural check.

**The TypeScript type** (`types/step.ts`):

```ts
export interface Step {
  readonly id: string;             // from `## Step: <id>`
  readonly meta?: Meta;            // the ```meta``` block
  readonly prose: string;          // the verbatim reason — authoritative for HOW
  readonly uses: readonly string[]; // [_uses: F] markers extracted from prose
}
```

**The grammar + binding.** A step whose prose tags a knowledge file via the
`[_uses:]` marker. From `design-mapping.md`:

````markdown
## Step: design_vpc

```meta
_writes_var: design
_knowledge: [knowledge/design/design-defaults.json]
```

After the loop, design `design.vpc_design` … build from
`design-defaults.json.new_vpc` `[_uses: design-defaults.json]` — `cidr_block`, …
````

binds to (prose abbreviated):

```ts
{
  id: "design_vpc",
  meta: { writesVar: "design", knowledge: ["knowledge/design/design-defaults.json"] },
  prose: "After the loop, design `design.vpc_design` … build from `design-defaults.json.new_vpc` …",
  uses: ["design-defaults.json"],   // extracted from the [_uses:] marker
}
```

The `uses` projection lets the `USES` check verify `["design-defaults.json"]` is a
subset of `meta.knowledge ∪ meta.templates` — turning a prose file-reference into
a checkable link instead of free-floating text.

---

### 3.3 `Orientation` — the one non-normative section

The single optional `## Orientation` section, right after the H1. The interpreter
READS it for context but MUST NOT execute it — it carries no binding rule. Modeled
as its own type (not a bare string) so the "recap-with-pointer only" check has a
home.

```ts
export interface Orientation { readonly prose: string; }
```

---

### 3.4 `Frontmatter` — the structural contract block

The `---`…`---` block: "the single source of truth for the unit's contract."
THREE distinct key-sets, so THREE types. Fragment and Assembler share a
`UnitFrontmatterCore`; Phase is its own (the composer) shape.

**The TypeScript types** (`types/frontmatter.ts`, abridged):

```ts
export interface UnitFrontmatterCore {
  readonly ofPhase: string;                       // _of_phase
  readonly scope: string;                         // _scope
  readonly produces: readonly string[];           // _produces
  readonly preconditions?: readonly Condition[];  // _preconditions
  readonly postconditions: readonly Condition[];  // _postconditions
  readonly onError: OnErrorTable;                 // _on_error
}

export interface FragmentFrontmatter extends UnitFrontmatterCore {
  readonly kind: "fragment";
  readonly fragment: string;                      // _fragment (id)
}

export interface AssemblerFrontmatter extends UnitFrontmatterCore {
  readonly kind: "assembler";
  readonly assemble: string;                      // _assemble (id)
  readonly reads?: readonly string[];             // _reads
  readonly mutates?: readonly string[];           // _mutates (the only mutator)
}

export interface PhaseFrontmatter {
  readonly kind: "phase";
  readonly phase: string;                         // _phase
  readonly requiresPhase: string | null;          // _requires_phase (null = first phase)
  readonly scope: string;                         // _scope
  readonly init?: InitBlock;                      // _init (first phase only)
  readonly reEntryGuard?: ReEntryGuard;           // _re_entry_guard
  readonly input: readonly string[];              // _input
  readonly knowledge?: readonly Guarded[];        // _knowledge (the SOLE load decision)
  readonly templates?: readonly Guarded[];        // _templates
  readonly fragments: readonly FragmentRef[];     // _fragments (ordered composition)
  readonly assemble: AssemblerRef;                // _assemble (the single assembler)
  readonly postconditions?: readonly Condition[]; // _postconditions (cross-cutting)
  readonly produces: readonly string[];           // _produces
  readonly advancesTo: string;                    // _advances_to
  readonly forbidsFiles?: readonly string[];      // _forbids_files
  readonly onError: OnErrorTable;                 // _on_error
  // (title?, preconditions? omitted for brevity)
}
```

**The composition payoff.** `PhaseFrontmatter` composes FIVE earlier types —
`ReEntryGuard`, `Condition[]`, `Guarded[]`, `FragmentRef[]` (→ `Trigger`),
`AssemblerRef`, and `OnErrorTable` (→ `ErrorAction`). Every guarantee below it
holds for free.

**The grammar + binding.** The discover phase frontmatter (abbreviated) binds to
a `PhaseFrontmatter`:

```yaml
_phase: discover
_requires_phase: null
_scope: "Inventory what exists on Heroku …"
_input: ["**/*.tf", "Procfile", "app.json", "**/*billing*.{csv,json}"]
_init: { _init_migration_run: true }
_re_entry_guard: { if: "…", action: _halt_and_inform, reason: stale_downstream, on_confirm: "…" }
_fragments:
  - { _id: terraform, _trigger: {…}, _file: phases/discover/discover-terraform.md }
  - { _id: billing,   _trigger: {…}, _file: phases/discover/discover-billing.md }
_assemble: { _file: phases/discover/discover-assemble.md }
_produces: [heroku-resource-inventory.json]
_advances_to: clarify
```

```ts
{
  kind: "phase",
  phase: "discover",
  requiresPhase: null,                       // → _init is REQUIRED iff this is null (a check)
  scope: "Inventory what exists on Heroku …",
  input: ["**/*.tf", "Procfile", "app.json", "**/*billing*.{csv,json}"],
  init: { verbs: { _init_migration_run: true } },   // shallow — see note
  reEntryGuard: { if: {condition:"…"}, action: {kind:"_halt_and_inform"}, reason: "stale_downstream", onConfirm: "…" },
  fragments: [ {id:"terraform", trigger:{…}, file:"…"}, {id:"billing", trigger:{…}, file:"…"} ],
  assemble: { file: "phases/discover/discover-assemble.md" },
  produces: ["heroku-resource-inventory.json"],
  advancesTo: "clarify",
  onError: { /* OnErrorTable */ },
}
```

> **`_init` is modeled shallowly.** It binds to `{ verbs: Record<string, unknown> }`
> — its verb sub-grammar (`_init_migration_run`, …) is NOT yet a closed union like
> `CheckVerb`, so a typo'd init-verb is not caught. This is a documented candidate
> for deepening later.

---

## Tier 4 — Unit types (the whole file, the apex)

A whole parsed `.md` file. Every unit is EXACTLY, in order: Frontmatter → H1 →
optional Orientation → zero-or-more Steps → nothing else. THREE kinds, discriminated
on `kind`, each pairing its matching `Frontmatter` with the shared body regions.

**The TypeScript types** (`types/unit.ts`):

```ts
export interface UnitRegions {
  readonly title?: string;             // the H1 (cosmetic)
  readonly orientation?: Orientation;  // the optional ## Orientation
  readonly steps: readonly Step[];     // the ## Step: sections, in order
}

export interface Phase     extends UnitRegions { readonly kind: "phase";     readonly frontmatter: PhaseFrontmatter; }
export interface Fragment  extends UnitRegions { readonly kind: "fragment";  readonly frontmatter: FragmentFrontmatter; }
export interface Assembler extends UnitRegions { readonly kind: "assembler"; readonly frontmatter: AssemblerFrontmatter; }

export type Unit = Phase | Fragment | Assembler;
```

**The composition apex.** A `Phase` transitively composes the entire system:
`PhaseFrontmatter → {ReEntryGuard, Condition[], Guarded[], FragmentRef[] (→ Trigger),
AssemblerRef, OnErrorTable (→ ErrorAction)}`, and the body `→ Step[] → Meta →
WhenCondition`. The whole typed graph meets at `Unit`. Validate a `Unit` and every
Tier-1 guarantee holds at the top for free.

**The kind-specific body rule.** The *shape* allows `steps: Step[]` for all three,
but a check enforces the invariant the shape can't: a **phase** has ZERO steps (its
work is the `_fragments`/`_assemble` composition); a **fragment/assembler** has
one-or-more. A phase with steps, or a fragment with none, is invalid.

**The grammar + binding.** The whole `discover.phase.md` file binds to:

```ts
{
  kind: "phase",
  frontmatter: { /* the PhaseFrontmatter from 3.4 */ },
  title: "Discover Heroku Resources",
  orientation: { prose: "Scan the workspace for Heroku declarations …" },
  steps: [],   // ZERO — a phase composes units; it has no steps of its own
}
```

A `discover-terraform.md` *fragment*, by contrast, binds to a `Fragment` with a
`FragmentFrontmatter` and a NON-empty `steps` array.

---

## How a `.md` file becomes a typed `Unit` (the pipeline)

The types say WHAT shape is valid; the parser EXTRACTS it. Two layers, one job
each (`scripts/dsl-validator/`):

```
text (.md file)
   │
   ▼  parser/split.ts        → frontmatter + H1 + Orientation + Step regions (pure structure)
   ▼  parser/yaml.ts         → YamlValue tree (pure SYNTAX, knows nothing about the DSL)
   │
   ▼  binders/*.ts           → typed values, BOTTOM-UP (one binder per type, Result-based)
   │     error-action → when-condition → check-verb → trigger        (Tier 1)
   │     condition → guarded → fragment-ref → re-entry-guard → …      (Tier 2)
   │     meta → step → orientation → frontmatter                      (Tier 3)
   │     unit                                                          (Tier 4)
   │
   ▼  checks/*.ts            → Findings (the rules the TYPES can't express)
   │
   ▼  validate.ts            → report → exit 1 on any error
```

Binders return `Result<T>` rather than throwing, so one pass collects MANY
findings. Only the pure-syntax YAML layer throws. Bind-time findings
(`CLOSED_VOCAB`, `BIND`, `FORM1_LEAK`, `YAML`) catch shape/vocab violations; the
check layer catches everything semantic (`SUBSET`, `USES`, `GUARD_SCOPE`,
`PRODUCES`, `XTABLE`, `BRANCH_COVERAGE`, …).

---

## The dividing line: what the types catch vs what they don't

This is the most important thing to internalize about the DSL.

**The types + binders catch STRUCTURE:** closed vocabulary (every `_`-key is
known), shape (a `_validate_schema` carries `{file, schema}`), composition (a
`Phase` has well-formed `_fragments`), and — via the check layer — cross-reference
integrity (every `_file` resolves, every step file ⊆ phase load set, every
producer-emitted class is a key in the consumer table).

**The types CANNOT catch VALUES.** A `_assert` binds to `{kind: "_assert",
condition: "<english>"}` — the *condition string is opaque*. The validator
verifies the assert is in `_postconditions`; it never reads what the assert says.
So a "pinned value" guarantee like `every standard SG cidr == default_inbound_cidr`
is enforced by the LLM at runtime, not by CI. Likewise a `WhenCondition` is an
un-parsed string. This is by design — "structure is checkable; judgment is the
LLM's" — but it means **structural completeness is completeness over composition,
refs, and shape, not over the values the skill emits.** When you read a green
`mise run lint:dsl`, that is what it is promising, and what it is not.

---

## Quick reference: every type, its tier, and its `_`-key

| Type | Tier | DSL grammar | Source file |
| ---- | ---- | ----------- | ----------- |
| `WhenCondition` | 1 | `_when:` value (4 contexts) | `types/when-condition.ts` |
| `ErrorAction` | 1 | `_halt_and_inform` / `_warn_and_skip` / `_defer` / `_default_and_warn` / `_unrecoverable` | `types/error-action.ts` |
| `CheckVerb` | 1 | `_check_*` / `_validate_*` / `_assert` (7) | `types/check-verb.ts` |
| `Trigger` | 1 | `_always` / `_glob` / `_artifact_exists` / `_check_source_exists` / `_when` (5) | `types/trigger.ts` |
| `Condition` | 2 | one `_preconditions` / `_postconditions` item | `types/condition.ts` |
| `Guarded` | 2 | one `_knowledge` / `_templates` entry | `types/guarded.ts` |
| `FragmentRef` | 2 | one `_fragments` entry `{_id,_trigger,_file}` | `types/fragment-ref.ts` |
| `AssemblerRef` | 2 | `_assemble: {_file}` (phase side) | `types/assembler-ref.ts` |
| `ReEntryGuard` | 2 | `_re_entry_guard: {if, action, reason, on_confirm}` | `types/re-entry-guard.ts` |
| `OnErrorTable` | 2 | `_on_error:` documentation block | `types/on-error-table.ts` |
| `Meta` | 3 | the ```` ```meta ```` block under a `## Step:` | `types/meta.ts` |
| `Step` | 3 | one `## Step: <id>` section | `types/step.ts` |
| `Orientation` | 3 | the one `## Orientation` section | `types/orientation.ts` |
| `Frontmatter` | 3 | the `---`…`---` block (3 kinds) | `types/frontmatter.ts` |
| `Unit` | 4 | the whole file (`Phase`/`Fragment`/`Assembler`) | `types/unit.ts` |

---

*See `dsl-types.md` for the canonical model — every parked nuance, the drift
contract, the toolchain conventions, and the per-type "validation power this
unlocks" notes. This guide is the on-ramp; that document is the specification.*
