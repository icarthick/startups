# Discover Refactor to `_routes` (uniform discoverers) — VERDICT

**Change:** discover's body went from inline `_steps` (+ a `_knowledge` billing
sub-file) to a `_routes` list of PEER discoverer sub-units, each in its own file:

- `phases/discover/discover-terraform.md` (route: required, always)
- `phases/discover/discover-billing.md` (route: optional, glob-triggered)
- `phases/discover/discover-assemble.md` (route: always, merges contributions)

**Motivation (user):** terraform and billing are the same KIND of thing (each
scans→parses→contributes to the inventory); treating one as inline steps and the
other as a `_knowledge` file was incoherent. `_knowledge` is for DATA (lookup
tables); billing is INSTRUCTIONS. Uniform discoverers as routes fixes both the
category error and the asymmetry. New shared construct `_routes` added to
INTERPRETER.md.

**Engine-plumbing avoided:** unlike the engine's routes.json (separate dispatched
files writing intermediate `_terraform-discovery.json` / `_billing-discovery.json`
across process boundaries), DSL routes run in ONE LLM pass into in-memory
accumulators — no intermediate artifacts. Only assemble `_writes` the inventory.

---

## Cold-LLM re-test: PASS — and the structure tested as LOWER mental-load

A cold LLM executed the refactored phase from INTERPRETER.md + discover.phase.md

- the route files + fixture. Results:

- **Route triggering correct:** all 3 triggers evaluated right; each `_file`
  loaded ONLY after its trigger was confirmed true; untriggered route files would
  not be read (context economy confirmed live).
- **Execution model confirmed:** "one continuous pass, in-memory accumulators, NO
  intermediate files... the absence of any `_writes` between routes makes that
  unambiguous." The plumbing trap was structurally avoided.
- **Same correct inventory:** 10 resources (9 TF + 1 Procfile-only formation),
  every hard case right (Procfile-only release, secret redaction, app.json-only
  sendgrid, detect-only pipeline, space peering, Cedar, billing enterprise_csv
  dyno_cost-not-dyno_units). Schema-valid. `HANDOFF_OK`.
- **Comprehensibility verdict (the design thesis):** "clear and lower-load than I
  expected... routes-vs-steps was unambiguous... arguably lower [load] for this
  phase" — the optional/triggered billing became a first-class skippable unit;
  the required path stayed clean. Confirms the uniform-discoverer model is the
  better mental model, by a fresh executor with no stake in the design.

## Two findings (both FIXED)

1. **Undeclared cross-route accumulators.** assemble consumed `parse_warnings`
   and `discovery_sources`, but no route's `_contributes` declared them — a
   contract gap the route model made visible (the LLM reasoned past it). **Fixed:**
   added both to the terraform + billing routes' `_contributes`.
2. **App↔space join underspecified** (the ONE thing the LLM had to guess).
   `heroku_space` is `unassociated`, but `apps[].space` had no population rule
   for a standalone space. Pre-existing in upstream; surfaced by the route
   contracts. **Fixed:** added an explicit join rule to discover-terraform's
   `detect_generation` — app `space` comes from the app's OWN `heroku_app.space`
   attr, else null; a standalone unreferenced `heroku_space` does not populate it.

## Net

The full uniform-discoverer refactor holds: routes are peers, run in one pass,
no intermediate artifacts, and a cold LLM finds the structure clearer than the
linear-steps form for this phase. `_routes` is now a proven shared construct
(reusable for generate's terraform/docs/scripts contributors later). Both
findings fixed. discover remains end-to-end cold-validated under the new
structure.
