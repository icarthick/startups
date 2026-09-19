# Render Discovery Schema

Schema for `render-resource-inventory.json`, produced by the Discover phase orchestrator (`discover.md`).

**Convention**: Values shown as `X|Y` in examples indicate allowed alternatives — use exactly one value per field, not the literal pipe character.

---

## render-resource-inventory.json (Phase 1 output)

Complete inventory of discovered Render resources. Uses a **flat resource model** — no clustering, no dependency graphs, no topological sorting. Resources are grouped by the `render_service` field.

```json
{
  "metadata": {
    "discovery_timestamp": "2026-09-19T10:30:00Z",
    "total_services_discovered": 4,
    "discovery_sources": ["render_yaml", "live"],
    "confidence": "full|reduced",
    "confidence_note": "Live capture failed for some services (if reduced)"
  },
  "resources": [
    {
      "resource_id": "web_service:my-web-app",
      "resource_type": "web_service",
      "render_service": "my-web-app",
      "config": {}
    }
  ]
}
```

---

## Top-Level Sections

### `metadata` (REQUIRED)

| Field                       | Type              | Required | Description                                                                                                                                                                       |
| --------------------------- | ----------------- | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `discovery_timestamp`       | string (ISO 8601) | ✅       | When discovery was executed                                                                                                                                                       |
| `total_services_discovered` | integer           | ✅       | Count of Render services found                                                                                                                                                    |
| `discovery_sources`         | string[]          | ✅       | Sources used: `"render_yaml"`, `"live"`                                                                                                                                           |
| `confidence`                | string            | ✅       | `"full"` (primary source(s) parsed/captured successfully) or `"reduced"` (partial data, e.g., render.yaml parse errors, failed/skipped live captures, missing expected resources) |
| `confidence_note`           | string            | ❌       | Explanation when confidence is `"reduced"`                                                                                                                                        |

### `resources[]` (REQUIRED)

Flat array of all discovered resources. **No nesting, no clustering.**

| Field            | Type    | Required | Description                                                                                                                     |
| ---------------- | ------- | -------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `resource_id`    | string  | ✅       | Unique identifier (format below)                                                                                                |
| `resource_type`  | string  | ✅       | One of: `"web_service"`, `"background_worker"`, `"cron_job"`, `"postgres"`, `"key_value"`, `"static_site"`, `"private_service"` |
| `render_service` | string  | ✅       | Service name this resource belongs to                                                                                           |
| `config`         | object  | ✅       | Type-specific configuration (see per-type schemas below)                                                                        |
| `source`         | string  | ❌       | Discovery provenance: `"render_yaml"`, `"live"`, or `"live+render_yaml"` (merged)                                               |
| `live_drift`     | boolean | ❌       | Set `true` when live discovery found the resource but render.yaml does not define it                                            |
| `not_found_live` | boolean | ❌       | Set `true` when render.yaml declares the resource but live discovery did not find it                                            |

---

## Resource ID Formats

Deterministic ID format per resource type:

| Resource Type       | ID Format                  | Example                           |
| ------------------- | -------------------------- | --------------------------------- |
| `web_service`       | `web_service:{name}`       | `web_service:my-web-app`          |
| `background_worker` | `background_worker:{name}` | `background_worker:my-worker`     |
| `cron_job`          | `cron_job:{name}`          | `cron_job:my-cron`                |
| `postgres`          | `postgres:{name}`          | `postgres:my-db`                  |
| `key_value`         | `key_value:{name}`         | `key_value:my-cache`              |
| `static_site`       | `static_site:{name}`       | `static_site:my-frontend`         |
| `private_service`   | `private_service:{name}`   | `private_service:my-internal-api` |

---

## Per-Type Config Schemas

### `web_service` config

```json
{
  "plan": "starter|standard|pro|pro_plus|pro_max|pro_ultra|free",
  "region": "oregon|ohio|virginia|frankfurt|singapore",
  "runtime": "docker|node|python|ruby|go|java|php|rust|elixir|static",
  "instance_count": 1,
  "autoscaling": false,
  "health_check_path": "/health",
  "config_var_keys": ["DATABASE_URL", "REDIS_URL"]
}
```

| Field               | Type           | Required | Description                                                   |
| ------------------- | -------------- | -------- | ------------------------------------------------------------- |
| `plan`              | string         | ✅       | Render plan tier, lowercased                                  |
| `region`            | string         | ✅       | Render region                                                 |
| `runtime`           | string         | ✅       | Runtime/build environment                                     |
| `instance_count`    | integer        | ✅       | Number of instances (from render.yaml `numInstances` or live) |
| `autoscaling`       | boolean        | ✅       | Whether autoscaling is enabled                                |
| `health_check_path` | string \| null | ❌       | HTTP health check path                                        |
| `config_var_keys`   | string[]       | ✅       | Environment variable KEY names — NEVER VALUES                 |

### `background_worker` config

```json
{
  "plan": "starter|standard|pro|pro_plus|pro_max|pro_ultra",
  "region": "oregon",
  "runtime": "docker|node|python",
  "instance_count": 1,
  "config_var_keys": ["DATABASE_URL"]
}
```

Same fields as `web_service` minus `health_check_path`.

### `cron_job` config

```json
{
  "plan": "starter|standard|pro",
  "region": "oregon",
  "runtime": "docker|node|python",
  "schedule": "0 5 * * *",
  "config_var_keys": []
}
```

| Field             | Type     | Required | Description                                   |
| ----------------- | -------- | -------- | --------------------------------------------- |
| `plan`            | string   | ✅       | Render plan tier                              |
| `region`          | string   | ✅       | Render region                                 |
| `runtime`         | string   | ✅       | Runtime environment                           |
| `schedule`        | string   | ✅       | Cron expression (5-field POSIX format)        |
| `config_var_keys` | string[] | ✅       | Environment variable KEY names — NEVER VALUES |

### `postgres` config

```json
{
  "plan": "free|starter|standard|pro|pro_plus",
  "region": "oregon",
  "postgres_version": "16",
  "estimated_storage_gb": null,
  "high_availability": false
}
```

| Field                  | Type           | Required | Description                                            |
| ---------------------- | -------------- | -------- | ------------------------------------------------------ |
| `plan`                 | string         | ✅       | Render Postgres plan tier                              |
| `region`               | string         | ✅       | Render region                                          |
| `postgres_version`     | string         | ✅       | Major version (e.g. `"16"`)                            |
| `estimated_storage_gb` | number \| null | ❌       | Storage in GB from live discovery; null if unavailable |
| `high_availability`    | boolean        | ✅       | Whether HA is enabled on the Render side               |

### `key_value` config

```json
{
  "plan": "free|starter|standard|pro",
  "region": "oregon",
  "redis_version": "7.0",
  "max_memory_policy": "noeviction"
}
```

| Field               | Type   | Required | Description                                               |
| ------------------- | ------ | -------- | --------------------------------------------------------- |
| `plan`              | string | ✅       | Render Key Value plan tier                                |
| `region`            | string | ✅       | Render region                                             |
| `redis_version`     | string | ✅       | Redis version (from live or render.yaml; default `"7.0"`) |
| `max_memory_policy` | string | ❌       | Redis maxmemory policy (from live discovery)              |

---

## Forbidden Fields

The following fields MUST NOT appear anywhere in `render-resource-inventory.json`. Their presence indicates accidental use of the GCP clustering model:

- `cluster_id`
- `creation_order_depth`
- `edges`
- `dependencies`
- `must_migrate_together`

The following fields are also FORBIDDEN — they indicate captured config var VALUES instead of key names:

- Any config field that looks like a connection string, password, or API key value
- Any `config_var_values` key (only `config_var_keys` is allowed)

---

## Grouping Rules

1. All resources in `resources[]` are flat — no nesting.
2. Resources belonging to the same Render service share an identical `render_service` value.
3. The `resources[]` array is flat — no nesting under service-level containers.

---

## Confidence Levels

| Level     | Meaning                                      | When Used                                                                             |
| --------- | -------------------------------------------- | ------------------------------------------------------------------------------------- |
| `full`    | Every source that ran produced complete data | render.yaml parsed without errors and/or every live capture succeeded                 |
| `reduced` | Partial data from at least one source        | render.yaml parse errors, failed/skipped live captures, or missing expected resources |

---

## Complete Example

```json
{
  "metadata": {
    "discovery_timestamp": "2026-09-19T10:30:00Z",
    "total_services_discovered": 4,
    "discovery_sources": ["render_yaml"],
    "confidence": "full"
  },
  "resources": [
    {
      "resource_id": "web_service:acme-api",
      "resource_type": "web_service",
      "render_service": "acme-api",
      "source": "render_yaml",
      "config": {
        "plan": "standard",
        "region": "oregon",
        "runtime": "docker",
        "instance_count": 1,
        "autoscaling": false,
        "health_check_path": "/health",
        "config_var_keys": ["DATABASE_URL", "REDIS_URL", "SECRET_KEY"]
      }
    },
    {
      "resource_id": "background_worker:acme-worker",
      "resource_type": "background_worker",
      "render_service": "acme-worker",
      "source": "render_yaml",
      "config": {
        "plan": "standard",
        "region": "oregon",
        "runtime": "docker",
        "instance_count": 2,
        "config_var_keys": ["DATABASE_URL", "REDIS_URL"]
      }
    },
    {
      "resource_id": "postgres:acme-db",
      "resource_type": "postgres",
      "render_service": "acme-db",
      "source": "render_yaml",
      "config": {
        "plan": "standard",
        "region": "oregon",
        "postgres_version": "16",
        "estimated_storage_gb": null,
        "high_availability": false
      }
    },
    {
      "resource_id": "key_value:acme-cache",
      "resource_type": "key_value",
      "render_service": "acme-cache",
      "source": "render_yaml",
      "config": {
        "plan": "starter",
        "region": "oregon",
        "redis_version": "7.0"
      }
    }
  ]
}
```

---

## Validation Checklist (used by Completion Handoff Gate)

1. ✅ `render-resource-inventory.json` exists with at least one resource entry
2. ✅ `metadata.discovery_timestamp` is set (ISO 8601)
3. ✅ `metadata.total_services_discovered` is set (integer ≥ 0)
4. ✅ `metadata.discovery_sources` is a non-empty array
5. ✅ `metadata.confidence` is `"full"` or `"reduced"`
6. ✅ Every entry in `resources[]` has: `resource_id`, `resource_type`, `render_service`, `config`
7. ✅ No forbidden clustering fields present anywhere in the document
8. ✅ No config var VALUES anywhere in the document — `config` entries carry key names only (`config_var_keys`)
9. ✅ If render.yaml discovery ran → resources include render_yaml-sourced entries
10. ✅ If live discovery ran → resources include live-sourced entries, and `"live"` is in `metadata.discovery_sources`
