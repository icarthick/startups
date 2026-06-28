# Re-entry Guard + Cascade — Cold-LLM Test VERDICT

**Question:** When the user re-runs the discover phase on a workspace that
already completed through clarify (so `preferences.json` exists), does the DSL
make a cold LLM (a) HALT without destroying anything, and (b) on explicit
confirmation, perform the correct cascade reset — all from `INTERPRETER.md` +
`discover.phase.md` alone?

**Setup:** Claude Code (fresh Bedrock session), zero repo/engine context. Given
only `INTERPRETER.md` + `phases/discover.phase.md` and the
`fixtures/acme-store-resumed/` workspace whose `migration-state/` has
`.phase-status.json` (discover+clarify completed), `preferences.json`, and a
prior `heroku-resource-inventory.json`.

**Result: PASS on intended behavior, with one real bug caught and fixed.**

---

## Part 1 — unconfirmed re-run: PASS

The cold LLM correctly:

- Evaluated the guard `if` (`preferences.json exists AND clarify completed`) →
  TRUE → fired the guard.
- **HALTED without running the steps and without overwriting the inventory.**
- Emitted `GATE_FAIL | phase=discover | field=preferences.json | reason=stale_downstream`
  and a clear user message.
- **Did NOT delete `preferences.json`** — quoting the interpreter: "fail-closed
  interlock, not a cleanup… you NEVER destroy the user's expensive downstream
  artifacts automatically." Exactly the design intent.

## Part 2 — confirmed re-run: PASS

On explicit confirmation it performed `on_confirm` precisely:

- Reset clarify/design/estimate/generate/feedback → `pending`, kept discover
  active.
- Removed exactly the listed downstream artifacts present (only
  `preferences.json` in this fixture), and correctly did NOT put
  `heroku-resource-inventory.json` (discover's own output) in the reset list —
  it's overwritten by the re-run instead.
- Ran the steps, re-evaluated the guard (now FALSE — `preferences.json` gone),
  passed, emitted `HANDOFF_OK | phase=discover | artifacts=heroku-resource-inventory.json`,
  advanced to clarify.

The cascade was **fully determined** by discover's inline `on_confirm` — the LLM
did not have to guess (the self-contained stopgap worked as intended while the
full phase chain is unauthored).

---

## The bug the test caught (now FIXED)

**Guard evaluation-order conflict.** The interpreter's master execution order
listed `_preconditions → _steps → _postconditions`, and `_re_entry_guard` is
authored in the `_postconditions` block. Read literally, that means the steps
run — **overwriting `heroku-resource-inventory.json`** — BEFORE the guard fires,
defeating the guard entirely. The cold LLM resolved it correctly only by
reasoning from the guard's prose + Golden Rule 3 ("structure/guardrail wins"),
and flagged that "a strict top-to-bottom reading would overwrite the inventory
first."

This is a genuine correctness bug, not a nitpick: the guardrail's value depends
entirely on firing before the destructive step.

**Fix applied (this session):**

1. INTERPRETER.md master order now reads
   `_init → _re_entry_guard (pre-steps) → _preconditions → _knowledge → _steps →
   _postconditions → advance`, with an explicit "why the guard moves up" note.
2. The `_re_entry_guard` definition now states **"Evaluation time: PRE-STEPS"**
   inline, so a reader jumping straight to the key sees it too.

After the fix, the guard is unambiguously a pre-steps interlock.

### Structural fix follow-up (re-tested) — guard promoted to top-level key

The first fix (hoisting via a "PRE-STEPS" note while leaving the guard authored
inside `_postconditions`) was a band-aid: the key still lived in a block whose
timing it contradicted. Resolved properly by **promoting `_re_entry_guard` to a
top-level phase key** (sibling of `_preconditions`), evaluated in its natural
position in the master order. The band-aid note was removed.

**Re-test (cold LLM, clean structure): PASS, and the ordering inference is GONE.**
Where the first run reported "I had to override the literal control flow using
the guard's intent," the re-test reported:

> "The interpreter told me directly; I did not have to infer the timing... no
> ambiguity and no conflict — three independent statements agree."

It fired the guard pre-steps, halted without deleting `preferences.json`, and (on
hypothetical confirmation) performed the exact cascade. The bug class
("authored-here-runs-there") is structurally eliminated, not prose-patched.

**Two NEW minor soft spots the re-test surfaced (lesser, not blocking):**

1. **"Explicit confirmation" is undefined** — the spec demands the user EXPLICITLY
   confirm the cascade but gives no canonical prompt or affirmation token. "re-run
   discover" alone is NOT confirmation of the destructive reset. Left to LLM
   judgment. Worth defining a confirmation contract (what the LLM must ask, what
   counts as yes) — candidate for a future interpreter addition.
2. **`on_confirm` downstream list is duplicated inline rather than derived** —
   discover hardcodes its downstream artifacts (self-contained stopgap) while the
   interpreter also defines the canonical chain-derived cascade. No present
   conflict, but a DRIFT RISK once the full chain exists: the inline list and the
   `_advances_to`/`_produces`-derived set could diverge. Resolve when 2+ phases
   are authored by switching discover to the derived cascade.

---

## Other findings (minor, accepted)

- `heroku-resource-inventory.json` is overwritten without ceremony on a confirmed
  re-run — intended idempotent behavior; acceptable.
- discover's final status transitions in_progress (during on_confirm) →
  completed (on advance) are temporally ordered, not contradictory — the LLM
  inferred this correctly.
- The chain-derived cascade fallback is NOT verifiable until later phases exist;
  discover's inline `on_confirm` covers it for now (by design).

---

## Net

The re-entry branch — previously specified-but-untested — is now **cold-LLM
tested on both paths (halt + cascade)** and produced the intended behavior. The
one structural bug (guard fired too late) is fixed in the interpreter. The
"clear preferences.json" concern that started this thread is resolved correctly:
the guard never auto-clears; the cascade clears only on explicit confirmation.

**Confidence: HIGH** that re-entry semantics hold for discover. The generic
chain-derived cascade remains to be validated once 2+ phases are authored.
