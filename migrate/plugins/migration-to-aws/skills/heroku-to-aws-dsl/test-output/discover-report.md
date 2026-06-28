# Discover Phase (DSL, Form 2b) — Cold-LLM Executability Test VERDICT

**Question:** Can a cold-context LLM (zero repo/engine knowledge) execute the
ported **discover** phase from `INTERPRETER.md` + `discover.phase.md` (Form 2b) +
the conditional `knowledge/discover-billing.md` alone, and produce a
schema-valid `heroku-resource-inventory.json` — *including the newly-ported
billing path*?

**Setup:** Claude Code (fresh Bedrock session), given ONLY the three DSL files +
`fixtures/acme-store/` (heroku.tf, Procfile, app.json, billing-export-2026-02.csv).
No access to main's markdown skill, the engine, or any prior context.

**Result: PASS.** The only failure was environmental — the Claude Code sandbox
denied filesystem writes, so the subagent computed the full artifact but couldn't
persist it. The computed artifact was transcribed to
`test-output/discover-inventory.actual.json` and validated:

- All 9 postcondition checks PASS (manual mirror).
- **Formal `jsonschema` validation against `heroku-resource-inventory.schema.json`: PASS.**
- Security check: the secret value `super-secret-value` appears NOWHERE in the output.
- Billing arithmetic: line items sum (200.0) == reported total (200.0).

---

## What this run proves (beyond the Form 1 discover test)

1. **Form 2b is as executable as Form 1.** The cold LLM correlated every
   ```` ```meta ```` fence to its step prose with **no trouble** ("co-location
   made correlation trivial; no frontmatter step-list to cross-reference"). The
   seam-free hybrid form holds for a real phase.

2. **The conditional `_knowledge` sub-file mechanism works.** The `_when` guard
   ("billing files exist") fired correctly — the LLM loaded `discover-billing.md`
   only because the fixture had a billing CSV, and followed it to parse the
   `enterprise_csv` format. This is the first test of the phase-file + conditional
   sub-file structure (the choice to mirror main's delegation).

3. **The interpreter-vocab fix held.** `_init` / `_init_migration_run` and
   `_check_source_exists` — added to the interpreter this session to close the
   gap the Form 1 test found — were all recognized. **Zero undefined `_`-keys**;
   the "undefined key => STOP" guardrail did not need to fire.

4. **All hard judgment calls correct**, identical to the Form 1 discover test
   plus the new ones:
   - Procfile-only `release` → synthesized `quantity:0, dyno_type:"unknown"`,
     `source:"procfile"`. ✓
   - Secret redaction (`config_var_keys` keys-only; `env_keys` keys-only). ✓
   - app.json-only `sendgrid:starter` → `app_json_only_addons`, NOT a resource;
     postgres/redis not duplicated (TF wins). ✓
   - Detect-only pipeline, space peering default `false`, Cedar from `heroku-22`. ✓
   - Billing CSV → `enterprise_csv`, 3 line items, sum reconciles. ✓

---

## The one real finding (port-time fix needed)

**`discover-billing.md` enterprise_csv parsing is AMBIGUOUS when both a
`dyno_units` and a `dyno_cost` column exist.** The knowledge file says
"`dyno_*`→dyno", but the fixture header has TWO `dyno_`-prefixed columns:
`dyno_units` (a count, 2) and `dyno_cost` (a dollar amount, 100.00). The cold LLM
made the correct judgment call (used `dyno_cost`, because line items are costs
and 100+75+25=200 reconciles with the `total` column; using `dyno_units`=2 would
break the cross-check), **but it had to guess** — the glob `dyno_*` doesn't say
which column is the cost.

**Fix:** tighten `knowledge/discover-billing.md` Step 2 enterprise_csv mapping to
name the cost column explicitly: prefer `dyno_cost` over `dyno_units`; the cost
line item is always the `*_cost`/`*_total` column, never a `*_units` count.
This is the discover analogue of the Form 1 test's "DSL must be self-contained"
finding — the rule existed in prose but was under-specified at a leaf.

Minor / cosmetic (not bugs):
- `discovery_timestamp` format unspecified → LLM used a deterministic placeholder.
  Runtime value is "now"; acceptable.
- `app_id: null` — the Heroku UUID isn't in local `.tf` (it's a remote computed
  attr). Schema allows null. Correct.

---

## Net

The full discover phase ported from main's RICHER discover.md (init + terraform +
Procfile/app.json + billing + route gates + re-entry guard) is **executable by a
cold LLM in Form 2b**, and the produced artifact **formally validates against the
schema**. One leaf-level ambiguity in the billing knowledge file was caught and
is a one-line fix.

**Confidence to proceed to the next phase (clarify): HIGH.** Discover is now
proven in the real skill layout, not just the scratchpad.

---

## Addendum: re-entry / cascade branch (tested separately)

The re-run-discover path (previously specified-but-untested) was cold-LLM tested
with a populated `.migration/` fixture (`fixtures/acme-store-resumed/`). Both
branches passed: unconfirmed re-run HALTS without deleting `preferences.json`;
explicit confirmation triggers the `on_confirm` cascade (reset downstream phases
+ remove their artifacts) then re-runs. The test caught one real bug — the
re-entry guard was evaluated too late (after steps overwrote the inventory) —
now fixed by hoisting the guard to pre-steps in INTERPRETER.md. Full writeup:
`test-output/reentry-cascade-verdict.md`.
