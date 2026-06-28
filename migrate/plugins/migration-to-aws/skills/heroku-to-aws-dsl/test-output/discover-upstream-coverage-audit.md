# Discover Port — Upstream Coverage Audit

**Question:** Did folding upstream's 3 discover files
(`discover.md` + `discover-terraform.md` + `discover-billing.md`) into the DSL
port drop any behavior? (The porting-skill warns this is exactly where logic
gets silently lost — cf. design.py dropping security groups / empty-Procfile /
rds_proxy / kafka-broker-by-tier.)

**Structure of the port (not all into one file):**
- `discover.md` (orchestrator) → `discover.phase.md` **frontmatter** + verbs in
  shared `INTERPRETER.md`.
- `discover-terraform.md` → **inlined** as `## Step:` sections in
  `discover.phase.md` (always-runs primary path).
- `discover-billing.md` → **separate** `knowledge/discover-billing.md`, loaded
  conditionally via the `_knowledge` `_when` guard (optional, heavy → sidecar).

So: terraform inlined, billing kept as a conditional sidecar (the user's
"mirror main's delegation" choice). The asymmetry mirrors upstream, which always
loads terraform discovery but only loads billing "if billing files found."

---

## Coverage result: full, after two gap fixes

### Gaps found and FIXED this session
1. **`_check_single_active_phase` (upstream Rule 2) was defined in the
   interpreter but not invoked by discover.** A real silent-drop. **Fixed:**
   added `_check_single_active_phase: true` to discover's `_preconditions` with
   `_on_failure: _halt_and_inform` (reason=invalid), restoring upstream Rule 2.
2. **Procfile→command route-gate (upstream Step 4 "SHOULD have command
   populated") was missing.** **Fixed:** added a postcondition `_assert` with
   `_on_failure: _warn_and_skip` (warning, not hard fail — matches the upstream
   SHOULD).

### Known limitation — INHERITED from upstream, NOT a regression
- **`line_item_csv` billing format is detected but has no parse rule.** It's in
  the detection table (Step 1) and the schema enum, but neither the DSL knowledge
  file's Step 2 NOR upstream's `discover-billing.md` Steps 2a–2e give it dedicated
  parsing logic. This thinness is faithfully carried over from upstream — fixing
  it would be a DIVERGENCE (inventing logic upstream lacks). Flagged for a
  separate "fix upstream too" decision; do NOT silently add parse logic here.

### Everything substantive confirmed ported (spot-checked file-by-file)
- All 7 Terraform resource types with full per-type extraction + attr rules
  (simple/nested-dot/ref/interp/map-keys-only secret redaction).
- Reference resolution (app lookup, unassociated fallback).
- `heroku_pipeline_coupling` → stages.
- Cedar/Fir detection from stack.
- Procfile + app.json integration (commands, buildpacks, env-keys,
  app_json_only_addons, Procfile-only formation synthesis).
- Full `.migration/` init flow (resume/fresh/cancel, .gitignore, .phase-status).
- All 4 error-handling rules (warn-skip / halt / unrecoverable / re-entry).
- Assembly rules: flat resources[], 4 required fields, apps[], metadata,
  terraform_metadata, billing_profile, forbidden-clustering-field guard.
- All 5 billing parse formats (enterprise_csv, invoice_csv, invoice_json,
  api_invoice_json, enterprise_json) + totals/per-app/validate/multi-file.

**Net:** the 3→(1 + sidecar) consolidation preserved everything substantive. Two
orchestration-layer gates were dropped in the first pass and are now restored.
One billing-format thinness is an inherited upstream limitation, explicitly NOT
patched to stay a faithful port.
