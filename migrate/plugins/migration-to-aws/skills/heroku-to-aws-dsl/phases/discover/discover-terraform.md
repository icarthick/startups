---
_fragment: terraform
_of_phase: discover
_scope: >
  Extract Heroku resource declarations from `.tf` files and integrate
  Procfile/app.json. ONLY this — no AWS names, no cost, no Terraform generation
  for AWS, no clustering. Writes the terraform-derived inventory data; does NOT
  write `.phase-status.json`.
_produces: [heroku-resource-inventory.json]
_postconditions:
  - { _assert: "resources[] has at least one entry", _on_failure: _unrecoverable }
  - _assert: "every resource has resource_id, resource_type, heroku_app, config"
  - _assert: "resources include source=='terraform' entries"
  - _assert: "apps[] present; metadata has discovery_timestamp AND total_apps_discovered"
  - { _assert: "if a Procfile or app.json was found -> formation resources for that app have command populated", _on_failure: _warn_and_skip }
_on_error:
  _warn_and_skip:   { effect: "record parse_warning; skip block/file/row; continue", status: continue }
  _unrecoverable:   { effect: "stop; surface error",                                 status: revert_to_pending }
---

# Discover Fragment: Terraform (primary)

## Orientation

A discover-phase FRAGMENT, triggered by `discover.phase.md` (its trigger is
effectively always — Terraform is the required primary source). Single
responsibility: discover Heroku resources from Terraform + repo artifacts, and
write them into `heroku-resource-inventory.json` (the assembler may
enrich/validate it afterward; this fragment is the file's CREATOR, the assembler
its MUTATOR). The written sections (`resources[]`, `apps[]`, `terraform_metadata`,
`metadata`) are shaped by `schemas/heroku-resource-inventory.schema.json`.

## Step: scan_terraform

```meta
_collect: [tf_files, parse_warnings]
```

Recursively glob `**/*.tf` (EXCLUDE `.terraform/`, `node_modules/`, `.git/`).
Keep only files containing a `resource "heroku_<type>"` block for the target
types:

- `heroku_app`, `heroku_addon`, `heroku_formation`, `heroku_domain`
- `heroku_config_association`, `heroku_pipeline`, `heroku_space`

Process matched files in **alphabetical order** for deterministic output.
(The phase precondition already guaranteed at least one such file exists.)

## Step: extract_resources

```meta
_for_each: tf_files
_collect: [resources, parse_warnings]
```

Parse each `.tf` file's `heroku_*` resource blocks. For each block extract
`tf_resource_type`, `tf_resource_name`, `tf_file`, and its attributes:

- simple attrs → `key: value`; nested blocks → dot notation
  (`organization.name`).
- Terraform refs (`heroku_app.x.id`) → `"ref:heroku_app.x.id"`; interpolations
  (`"${var.n}"`) → `"var:n"`; literals as-is.
- map attrs (e.g. `vars`) → record **key names only** (redact values — security).

Per-type field extraction:

- `heroku_app` → `app_name`(name), `region`, `stack`, `space`,
  `organization`(organization.name), `buildpacks[]`, `acm_enabled`(acm).
- `heroku_addon.plan` `"service:tier"` → `addon_service` + `plan`; `provider`
  defaults `"heroku"`. Unparseable plan → `plan:"unknown"`, continue.
- `heroku_formation` → `process_type`(type) / `quantity`(int) / `dyno_type`(size);
  `command` set to `null` here (Procfile fills it in `integrate_repo_artifacts`).
- `heroku_domain` → `hostname`, `sni_endpoint`(sni_endpoint_id).
- `heroku_config_association.vars` → `config_var_keys` (keys only).
- `heroku_pipeline` → `pipeline_name`; `stages:[]`, `review_apps_enabled:false`,
  `detection_status:"detect-only"`.
- `heroku_space` → `space_name`, `region`, `shield`(default false),
  `organization`, and a `peering` block `{detected:false, vpc_id:null,
  peer_cidr:null}` (Terraform alone cannot detect peering unless a peering
  resource is present).

**Reference resolution:** build a `heroku_app` name lookup
(`tf_resource_name` → `name`); resolve `app_id` refs to the app name; literal
app names/UUIDs used directly; unresolvable → `heroku_app="unassociated"`.
Spaces and pipelines are `heroku_app="unassociated"`.

Malformed block → record in `parse_warnings` and **skip** (`_warn_and_skip`), do
NOT halt. Missing required `heroku_app.name` → skip that resource + warn.

## Step: map_to_inventory

```meta
_collect: [resources]
```

Transform each extracted resource into a standard inventory entry:
`{ resource_id, resource_type, heroku_app, config, source: "terraform",
tf_file, tf_resource_name }`.

`resource_id` / `resource_type` by source type:

- `heroku_app` → `app:{name}` / `app`
- `heroku_addon` → `addon:{app}:{service}:{plan}` / `addon`
- `heroku_formation` → `formation:{app}:{type}` / `formation`
- `heroku_domain` → `domain:{app}:{host}` / `domain`
- `heroku_config_association` → `config:{app}` / `config`
- `heroku_pipeline` → `pipeline:{name}` / `pipeline`
- `heroku_space` → `space:{name}` / `space`

If `heroku_pipeline_coupling` resources are present, populate the pipeline's
`stages[]` with `{stage, app}` entries.

## Step: integrate_repo_artifacts

```meta
_collect: [resources, apps, parse_warnings]
```

**Procfile** (root or app subdir): parse `type: command` lines (`#` comments and
blank lines ignored; process type `[A-Za-z0-9_-]+`).

- Matching formation (same app + process type) → add `command`.
- Procfile-only process (no Terraform formation) → add a formation with
  `quantity:0, dyno_type:"unknown"`, `command` from Procfile, and
  `source:"procfile"` (NOT terraform).
- Missing Procfile → formation `command` stays `null`, continue.
- Parse error → `procfile_parse_warning` on the app entry, continue.

**app.json**: parse as JSON and extract as SUPPLEMENTARY context (Terraform wins
on conflict):

- `addons` → record any declared in app.json but not Terraform as the app's
  `app_json_only_addons[]` (do NOT make them first-class resources).
- `formation` → supplementary defaults only (Terraform values take precedence).
- `buildpacks` → record on the app (`buildpacks[]`).
- `env` → record KEY NAMES only (`env_keys[]`).
- `stack` → supplements generation detection below.
- Missing → continue; parse error → `app_json_parse_warning`, continue.

## Step: detect_generation

```meta
_collect: [apps]
```

Per app, from `stack` (Terraform or app.json): contains `heroku-20`/`heroku-22`/
`heroku-24` → `heroku_generation="cedar"`; contains `fir` or `cnb` →
`"fir"`; other/absent → `"unknown"`. Always set
`generation_action="detect_only"` (v1). **NEVER** emit ARM/Graviton/CNB config —
detection only.

**App→space linkage:** set the app entry's `space` field from the app's OWN
`heroku_app.space` attribute if present; otherwise `null`. Do NOT infer a link
from a standalone `heroku_space` resource that the app does not reference — a
`heroku_space` with no app referencing it stays an `unassociated` space resource
and does not populate any app's `space`. (Terraform alone cannot prove an app
runs in a given space unless the app declares it.)
