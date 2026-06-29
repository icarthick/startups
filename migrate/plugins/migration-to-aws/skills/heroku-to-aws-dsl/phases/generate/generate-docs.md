---
_fragment: docs
_of_phase: generate
_scope: >
  Fill the doc + script templates with conditional sections and write
  MIGRATION_GUIDE.md, README.md, and the scripts/ migration scripts. ONLY this.
  Does NOT update .phase-status.json.
_produces: [MIGRATION_GUIDE.md, README.md, scripts/]
_postconditions:
  - _check_file_exists: [MIGRATION_GUIDE.md, README.md]
  - _assert: "MIGRATION_GUIDE.md has Prerequisites + Phase 1 + Verification sections"
  - _assert: "a data-store migration section appears IFF that data store is in the design (no empty sections)"
  - _assert: "if Postgres in design -> scripts/migrate-postgres.sh exists; if Redis -> scripts/migrate-redis.sh exists"
  - _assert: "scripts are executable and contain {{...}} connection placeholders (not real credentials)"
  - { _assert: "README.md lists only files that were actually emitted", _on_failure: _warn_and_skip }
_on_error:
  _warn_and_skip:   { effect: "log warning; skip this file; continue", status: continue }
  _unrecoverable:   { effect: "stop; surface error",                   status: revert_to_pending }
---

# Generate Fragment: Docs + Scripts

## Orientation

The documentation/scripts FRAGMENT, triggered always by `generate.phase.md`. It
fills the `templates/generate/docs/` and `templates/generate/scripts/` templates
with conditional sections and writes `MIGRATION_GUIDE.md`, `README.md`, and the
`scripts/` migration scripts. INDEPENDENT of the terraform fragment (different
templates, different artifacts — it does not read terraform's output, only the
same design/preferences inputs). The doc/script bodies are templates (data); this
fragment fills placeholders + selects conditional sections. Does NOT update
`.phase-status.json`.

## Step: detect_flags

```meta
_writes_var: doc_flags
```

Scan `aws-design.json.services[]` + `preferences.json` to set the template
condition flags: `has_postgres` (RDS/Aurora present), `has_redis`
(ElastiCache), `has_kafka` (MSK), `has_any_datastore` (any of the three),
`has_compute`/`has_database`/`has_cache`/`has_messaging` (domain presence for the
README rows), `needs_containerization`
(`preferences.operational.containerization_status != "containerized"`),
`interim_cutover` (`preferences.global.migration_approach ==
"interim_cutover_data_first"`), `migration_method_*` (which method), and
`deferred_addons` (`aws-design.json.deferred[]`).
`generation_warnings_exist` = `generation-warnings.json.total_warnings > 0`.

## Step: write_guide_and_readme

```meta
_writes: [MIGRATION_GUIDE.md, README.md]
_templates: [templates/generate/docs/MIGRATION_GUIDE.md.tmpl, templates/generate/docs/README.md.tmpl]
```

Fill `MIGRATION_GUIDE.md.tmpl` `[_uses: MIGRATION_GUIDE.md.tmpl]` and `README.md.tmpl` `[_uses: README.md.tmpl]`, resolving `{{key}}` and
evaluating `{{IF cond}}`/`{{FOR x IN list}}` against `doc_flags` + the inputs.
**Strict no-empty-sections rule:** include a data-store migration section (and
its ToC entry) ONLY when its flag is true; OMIT the entire heading+content
otherwise; if ALL data-store flags are false, omit Phase 2 entirely. The README
table includes a row ONLY for a file that was actually emitted (gate the
compute/database/cache/messaging/script/warnings rows on the matching flag).
Use `{{PLACEHOLDER}}` form for connection values the user fills (never real
credentials). `{{estimated_monthly_total}}` from
`estimation-infra.json.projected_costs.aws_monthly_balanced`.

## Step: write_scripts

```meta
_templates: [templates/generate/scripts/migrate-postgres.sh, templates/generate/scripts/migrate-redis.sh]
```

Write `$MIGRATION_DIR/scripts/migrate-postgres.sh` when `has_postgres`, and
`scripts/migrate-redis.sh` `[_uses: migrate-redis.sh]` when `has_redis` (copy the templates verbatim — their
`{{...}}` connection params are filled by the USER, not at generation time). Make
each written script executable (chmod +x). Kafka gets NO standalone script
(MirrorMaker config is environment-specific; the guide covers it).
