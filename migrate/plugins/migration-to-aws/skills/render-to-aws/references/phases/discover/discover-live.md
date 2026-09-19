---
_fragment: live
_of_phase: discover
_trigger:
  _when: "$MIGRATION_DIR/live-capture/manifest.json exists (the live-capture pre-work ran — consent was given and CLI commands completed)"
_contributes:
  - render-resource-inventory.json (live-sourced resource entries merged by the assembler)
---

# Discover Phase: Live Fragment

> Self-contained live-parse sub-file. Runs only when `$MIGRATION_DIR/live-capture/manifest.json`
> exists — meaning the main-window live-capture pre-work already ran, asked for consent, and
> wrote raw CLI output to `$MIGRATION_DIR/live-capture/`. This fragment reads those files and
> maps them to resource entries with `source: "live"`. Writing the inventory is owned by
> the assembler (`discover-assemble.md`).

**Execute ALL steps in order. Do not skip or deviate.**

---

## Step 1: Read the Capture Manifest

Read `$MIGRATION_DIR/live-capture/manifest.json`. It declares which captures completed
and the path to each output file.

```json
{
  "capture_timestamp": "<ISO timestamp>",
  "render_api_key_present": true,
  "commands_run": [
    {
      "cmd": "render services list --output json",
      "output_file": "services-list.json",
      "status": "ok"
    },
    { "cmd": "render services info <id>", "output_file": "service-<id>.json", "status": "ok" }
  ]
}
```

Only process captures with `"status": "ok"`. Record captures with any other status in
`live_metadata.capture_failures[]` (include `cmd`, `status`, and any error message), then continue.

If the manifest file itself cannot be read or parsed, abort this fragment with warning
"live-capture/manifest.json unreadable — live fragment skipped." and exit cleanly with
no output.

---

## Step 2: Parse Services List

Read `$MIGRATION_DIR/live-capture/services-list.json`. This is the output of
`render services list --output json`. Parse each service object in the returned array.

If the file cannot be parsed as JSON, record the error and exit cleanly with no output.

### Service Type Mapping

| Render `type` field | `service_type` in inventory      |
| ------------------- | -------------------------------- |
| `web_service`       | `web_service`                    |
| `background_worker` | `background_worker`              |
| `cron_job`          | `cron_job`                       |
| `static_site`       | `static_site` (out of scope)     |
| `private_service`   | `private_service` (out of scope) |
| `pserv`             | `private_service` (out of scope) |

### Service ID Generation

`service_id` is derived deterministically from the service `name` and `service_type`:

| service_type        | service_id format        |
| ------------------- | ------------------------ |
| `web_service`       | `web:{service_name}`     |
| `background_worker` | `worker:{service_name}`  |
| `cron_job`          | `cron:{service_name}`    |
| `static_site`       | `static:{service_name}`  |
| `private_service`   | `private:{service_name}` |

Normalize `service_name`: lowercase, replace whitespace with hyphens.

### Per-Service Entry Shape

For each service in the list (except out-of-scope types):

```json
{
  "service_id": "<generated per table above>",
  "service_type": "<mapped type>",
  "name": "<service name from API>",
  "plan": "<plan tier slug — e.g., standard, pro>",
  "region": "<render region — e.g., oregon, ohio, frankfurt>",
  "source": "live",
  "config": { "<type-specific fields — see Step 3>" }
}
```

For out-of-scope types (`static_site`, `private_service`), still record a stub entry with
`source: "live"` and `out_of_scope: true` — the assembler routes these to
`out_of_scope_services[]`. Do not discard them silently.

---

## Step 3: Parse Per-Service Detail Files (if available)

For each service that has a corresponding `service-<id>.json` capture in the manifest,
read that file to enrich the entry from Step 2.

Per-service detail files (from `render services info <id>`) contain more granular
configuration than the list output. Extract the following per service type:

### `web_service` enrichment

| Source field      | Inventory field            | Notes                            |
| ----------------- | -------------------------- | -------------------------------- |
| `healthCheckPath` | `config.health_check_path` | Optional                         |
| `numInstances`    | `config.num_instances`     | Current live instance count      |
| `autoDeploy`      | `config.auto_deploy`       | boolean                          |
| `customDomains[]` | `config.custom_domains[]`  | Domain names only, no certs/keys |

### `background_worker` enrichment

| Source field   | Inventory field        | Notes                       |
| -------------- | ---------------------- | --------------------------- |
| `numInstances` | `config.num_instances` | Current live instance count |
| `autoDeploy`   | `config.auto_deploy`   | boolean                     |

### `cron_job` enrichment

| Source field | Inventory field      | Notes                    |
| ------------ | -------------------- | ------------------------ |
| `schedule`   | `config.schedule`    | Cron expression string   |
| `lastRunAt`  | `config.last_run_at` | ISO timestamp (optional) |

### `postgres` enrichment

| Source field           | Inventory field                 | Notes                     |
| ---------------------- | ------------------------------- | ------------------------- |
| `postgresMajorVersion` | `config.postgres_major_version` | e.g., `"16"`              |
| `storageGB`            | `config.storage_gb`             | Current allocated storage |
| `highAvailability`     | `config.high_availability`      | boolean                   |

### `key_value` enrichment

| Source field      | Inventory field            | Notes               |
| ----------------- | -------------------------- | ------------------- |
| `maxmemoryPolicy` | `config.max_memory_policy` | e.g., `allkeys-lru` |

---

## Step 4: Extract Environment Variable Keys (ALL service types)

**CRITICAL SECURITY CONSTRAINT:** Env var VALUES must NEVER appear in the inventory.
Record only the KEY names.

For each service detail file, find the environment variables section (often `envVars`,
`env`, or a separate env endpoint response). Extract ONLY the key names:

```json
"config": {
  "env_var_keys": ["DATABASE_URL", "REDIS_URL", "SECRET_KEY"]
}
```

Apply the following guards when extracting key names:

- Reject any entry that contains an `=` sign (it is a KEY=VALUE pair — split it and
  keep only the key portion before `=`)
- Reject any key name longer than 256 characters (malformed)
- Reject any key name that looks like a secret value (e.g., starts with `-----BEGIN`,
  contains whitespace, looks like a URL with embedded credentials)
- Anything that does not look like an environment variable name (uppercase letters,
  numbers, underscores) should be rejected with a `config_redaction_warning` logged

If an env-var endpoint returns values mixed with keys (e.g., a JSON object where values
are exposed), extract ONLY the object's keys. Do NOT record the values. Log a
`config_redaction_warning` noting that values were present and were discarded.

---

## Step 5: Handle Discovery Failures and Out-of-Scope Services

### Partial Failures

If an individual service detail file is missing or fails to parse (capture status
`"failed"` in the manifest, or file unreadable), record the service in
`live_metadata.capture_failures[]` with the service id and reason:

```json
{ "service_id": "web:my-api", "reason": "service info capture failed: 404 Not Found" }
```

Continue with the remaining services. Set `live_metadata.confidence` to `"reduced"`
if ANY individual capture failed.

### Out-of-Scope Services

`static_site` and `private_service` entries are still recorded in the live fragment
output (with `out_of_scope: true`), so the assembler can populate
`out_of_scope_services[]` with them. Do NOT skip them silently.

---

## Step 6: Build live_metadata Contribution

Assemble the following `live_metadata` object for the assembler:

```json
{
  "live_metadata": {
    "found": true,
    "captured_at": "<capture_timestamp from manifest>",
    "services_captured": N,
    "services_failed": M,
    "capture_warnings": ["<any warnings from manifest or parsing>"],
    "confidence": "high|reduced"
  }
}
```

Set `services_captured` to the count of services successfully parsed.
Set `services_failed` to the count of captures with non-`ok` status.
Set `confidence` to `"reduced"` if any captures failed or any config_redaction_warnings
were issued.

Note: the `drift` sub-object (if both render.yaml and live ran) is computed and added by
the assembler (`discover-assemble.md`), not by this fragment.

---

## Step 7: Pass Contribution to Assembler

When this fragment completes, the following are ready for the assembler
(`discover-assemble.md`):

1. **All live-sourced resource entries** — array of service objects with `source: "live"`
2. **`live_metadata` object** — as built in Step 6
3. **Any `capture_failures[]` and `config_redaction_warnings[]`** — to be merged into
   `live_metadata` and `metadata.confidence` by the assembler

The assembler merges live and render.yaml sources, resolves conflicts per the Merge &
Drift Rules, and writes the final `render-resource-inventory.json`. Do NOT write the
inventory file from this fragment.

---

## Scope Boundary

**This fragment covers live CLI output PARSING ONLY.**

FORBIDDEN — Do NOT include ANY of:

- AWS service names, recommendations, or equivalents
- Migration strategies, phases, or timelines
- Terraform generation for AWS
- Cost estimates or comparisons
- Effort estimates
- Running CLI commands (capture already ran in the main window pre-work; this fragment
  only reads the output files that were produced)

**Your ONLY job: Parse the pre-captured Render CLI output files and produce inventory
entries. Nothing else.**
