---
_fragment: collect
_of_phase: feedback
_scope: >
  Detect IDE/version, build an anonymized trace, present the survey URL,
  optionally build a shareable plan link (shell-out encode, non-blocking), and
  write trace.json + feedback.json. ONLY this. Does NOT update .phase-status.json.
_produces: [trace.json, feedback.json]
_postconditions:
  - _validate_json: feedback.json
  - _validate_schema: { file: feedback.json, schema: schemas/feedback.schema.json }
  - { _assert: "if trace_included == true -> trace.json exists and validates against schemas/feedback-trace.schema.json", _on_failure: _warn_and_skip }
  - _assert: "trace.json (if written) contains NO resource names, file paths, account IDs, or secrets \u2014 counts/types/enums only"
  - _assert: "survey_url starts with https:// and embeds the sanitized ide + plugin_version"
_on_error:
  _warn_and_skip:   { effect: "record warning; skip the optional item; continue", status: continue }
  _halt_and_inform: { effect: "stop; surface diagnostic",                          status: retain_in_progress }
---

# Feedback Fragment: Collect

## Orientation

The single feedback-phase FRAGMENT, triggered always by `feedback.phase.md`. It
reads `.phase-status.json` + whatever migration artifacts exist, then writes
`trace.json` + `feedback.json` (and optionally presents a share link). Config
(survey URL, IDE detection map, share-link rules, redaction patterns) is
`knowledge/feedback/feedback-config.json`; output shapes are the feedback +
trace schemas. The encoding of the optional share link is the one non-LLM
leaf — done by shelling out. Does NOT update `.phase-status.json`.

## Step: detect_ide_and_version

```meta
_writes_var: env
_knowledge: [knowledge/feedback/feedback-config.json]
```

Per `feedback-config.json.ide_detection` `[_uses: feedback-config.json]`, set `ide` from the environment (first
rule whose env var is set / context matches), else the `fallback` (`unknown`).
Set `plugin_version` from the nearest `plugin.json` `version`, else `0.0.0`.
Sanitize BOTH to `[a-zA-Z0-9._~-]`. (Env-dependent — not deterministic across
environments; that is expected and fine for telemetry.)

## Step: build_trace

```meta
_writes: trace.json
_knowledge: [knowledge/feedback/feedback-config.json]
```

Build an ANONYMIZED trace (shape per `schemas/feedback-trace.schema.json`) from
the artifacts present in `$MIGRATION_DIR/`. Include a section ONLY if its
artifact exists:

- `migration_id` + `skill` + `phases_completed` (from `.phase-status.json`).
- `discovery` (from inventory): `total_apps`, `total_resources`,
  `resource_type_counts`, `discovery_sources`, `confidence`.
- `preferences` (from preferences.json): `questions_asked_count`,
  `questions_defaulted_count`.
- `design` (from aws-design.json): `total_services`, `deferred_count`,
  `warnings_count`.
- `estimation` (from estimation-infra.json): `pricing_source`,
  `projected_monthly`.
- `artifacts`: `terraform_file_count`.

**NEVER include resource names, file paths, account IDs, or secrets** — counts,
types, and enums only. Specifically: `discovery_sources` is the source-TYPE enum
(`terraform`/`procfile`/`billing`), NOT billing filenames; `resource_type_counts`
keys are resource TYPES, not ids; never copy an artifact object wholesale (it
carries names/paths). If a value isn't a count, a known enum, or a numeric, it
does not belong in the trace. Write `trace.json`. If trace building fails, set
`trace_included = false` and skip to `write_feedback` (`_warn_and_skip`).

## Step: present_survey

```meta
_knowledge: [knowledge/feedback/feedback-config.json]
```

Display the pretty-printed `trace.json`, then a single-line minified version for
copy-paste, then the survey URL built from `survey.base_url` + `survey.query`
(filling the sanitized `{ide}` + `{plugin_version}`) and an instruction to answer
the questions and paste the trace into the optional field.

## Step: maybe_share_link

```meta
_when: "preferences.json and estimation-infra.json both exist AND a share was requested (.phase-status.json.share_requested == true OR preferences.metadata.share_requested == true) — per feedback-config.json.share_link.enabled_when; else skip"
_knowledge: [knowledge/feedback/feedback-config.json]
```

OPTIONAL + NON-BLOCKING. Build the share-link payload per
`share_link.schema_version` and the payload fields (clarify_answers,
cost_summary, detected_services, resource_names, workload_types, spend_band per
the thresholds, share_checkpoint, phases_completed). REDACT secrets in
`clarify_answers` per `redaction.patterns` (replace with `[REDACTED]`).

ENCODE by SHELL-OUT (the one non-LLM-deterministic leaf): minify the payload
JSON, then run `share_link.encode.shell` (`gzip -c | base64 | tr '+/' '-_' | tr
-d '='`) to get the Base64URL string; the URL is `share_link.base_url` with
`{base64url_payload}` filled. If the encoded URL exceeds
`share_link.size_cap_chars`, apply `truncation_order`; if still too large, or any
encode step fails, SKIP the link (record `share_link_presented = false`) — NEVER
halt. On success, present the URL and set `share_link_presented = true`,
`share_link_generated_at` (now), `share_checkpoint`.

## Step: write_feedback

```meta
_writes: feedback.json
_knowledge: [knowledge/feedback/feedback-config.json]
```

Write `$MIGRATION_DIR/feedback.json` (shape per `schemas/feedback.schema.json`):
`timestamp` (ISO 8601 UTC), `skill`, `survey_url`,
`phases_completed_at_feedback`, `trace_included` (false if the trace failed),
`share_link_presented` (+ `share_link_generated_at` / `share_checkpoint` when a
link was produced, else null).
