---
_fragment: render-yaml
_of_phase: discover
_contributes:
  - render-resource-inventory.json (resource entries, services, metadata, render_yaml_metadata sections)
---

# Discover Phase: render.yaml Discovery (Primary Path)

> Self-contained render.yaml discovery sub-file. Scans for `render.yaml` in the
> workspace, parses all `services[]` entries, maps each service `type` to a
> `service_type` in the inventory format, and extracts plan, region, and configuration.
> If no `render.yaml` is found, exits cleanly with no output.

**Execute ALL steps in order. Do not skip or optimize.**

---

## Step 0: Locate render.yaml

Search the workspace root and immediate subdirectories for `render.yaml` (case-sensitive).

If no `render.yaml` found: log "No render.yaml found in workspace." and exit cleanly with no output. The assembler will rely solely on the live fragment (if it ran).

If found: record the path as `$RENDER_YAML_PATH` and continue.

---

## Step 1: Parse render.yaml

Read and parse `$RENDER_YAML_PATH` as YAML. The top-level `services` key is a list of service definitions. Each entry describes one deployable unit.

### 1a. Top-Level Structure

```yaml
services:
  - type: web_service
    name: my-web
    plan: standard
    region: oregon
    ...
  - type: background_worker
    name: my-worker
    plan: starter
    ...
  - type: cron_job
    name: my-cron
    plan: starter
    schedule: "0 * * * *"
    ...
  - type: postgres
    name: my-db
    plan: standard
    ...
  - type: key_value
    name: my-redis
    plan: starter
    ...
```

### 1b. Supported Service Types

| render.yaml `type`    | Inventory `service_type` | Notes                              |
| --------------------- | ------------------------ | ---------------------------------- |
| `web_service`         | `web_service`            | HTTP/HTTPS web application         |
| `background_worker`   | `background_worker`      | Persistent background process      |
| `cron_job`            | `cron_job`               | Scheduled job                      |
| `pserv` (private)     | `private_service`        | Internal service — OUT OF SCOPE v1 |
| `static_site`         | `static_site`            | Static site — OUT OF SCOPE v1      |
| `postgres`            | `postgres`               | PostgreSQL database                |
| `redis` / `key_value` | `key_value`              | Redis/key-value store              |

**Unsupported / out-of-scope types** (`static_site`, `private_service`/`pserv`):
Record in `deferred[]` with `reason: "out of scope in v1"` and continue — do NOT
halt parsing. Still add them to `metadata.out_of_scope_service_types[]` for visibility.

### 1c. Common Fields Per Service

Extract the following for every service entry:

| render.yaml field     | Inventory field          | Notes                                     |
| --------------------- | ------------------------ | ----------------------------------------- |
| `name`                | `name`                   | Required — used to generate `service_id`  |
| `type`                | `service_type`           | Mapped per 1b table above                 |
| `plan`                | `plan`                   | e.g., `free`, `starter`, `standard`, etc. |
| `region`              | `region`                 | e.g., `oregon`, `ohio`, `frankfurt`       |
| `envVars` (keys only) | `config.env_var_keys[]`  | Record key names ONLY, never values       |
| `dockerfilePath`      | `config.dockerfile_path` | Optional — if Dockerfile specified        |
| `buildCommand`        | `config.build_command`   | Optional                                  |
| `startCommand`        | `config.start_command`   | Optional                                  |

### 1d. Type-Specific Fields

#### `web_service`

| render.yaml field | Inventory field                        |
| ----------------- | -------------------------------------- |
| `healthCheckPath` | `config.health_check_path`             |
| `numInstances`    | `config.num_instances`                 |
| `autoDeploy`      | `config.auto_deploy`                   |
| `domains`         | `config.custom_domains[]` (names only) |

#### `background_worker`

| render.yaml field | Inventory field        |
| ----------------- | ---------------------- |
| `numInstances`    | `config.num_instances` |
| `autoDeploy`      | `config.auto_deploy`   |

#### `cron_job`

| render.yaml field | Inventory field                     |
| ----------------- | ----------------------------------- |
| `schedule`        | `config.schedule` (cron expression) |

#### `postgres`

| render.yaml field      | Inventory field                        |
| ---------------------- | -------------------------------------- |
| `databaseName`         | `config.database_name`                 |
| `user`                 | `config.user` (name only, no password) |
| `postgresMajorVersion` | `config.postgres_major_version`        |
| `highAvailability`     | `config.high_availability`             |

#### `key_value` / `redis`

| render.yaml field | Inventory field            |
| ----------------- | -------------------------- |
| `maxMemoryPolicy` | `config.max_memory_policy` |

### 1e. Parse Error Handling

If a service entry is missing required fields (`name` or `type`):

- Log warning: "Service entry missing required field at index {N}: {error}. Skipping."
- Skip the entry and continue.
- Record warning in `parse_warnings[]`.

If the entire render.yaml fails to parse:

- Log warning: "Failed to parse render.yaml: {error}."
- Exit cleanly with no output. The phase falls back to the live fragment.

---

## Step 2: Map to Inventory Format

### 2a. Service ID Generation

`service_id` is derived deterministically:

| service_type        | ID Format                           |
| ------------------- | ----------------------------------- |
| `web_service`       | `web:{service_name}`                |
| `background_worker` | `worker:{service_name}`             |
| `cron_job`          | `cron:{service_name}`               |
| `postgres`          | `postgres:{service_name}`           |
| `key_value`         | `redis:{service_name}`              |
| `static_site`       | `static:{service_name}` (deferred)  |
| `private_service`   | `private:{service_name}` (deferred) |

### 2b. Resource Entry Structure

Each service becomes a standard inventory entry:

```json
{
  "service_id": "<generated per 2a>",
  "service_type": "<mapped type>",
  "name": "<service name from render.yaml>",
  "plan": "<plan from render.yaml>",
  "region": "<region from render.yaml>",
  "config": { "<extracted attributes>" },
  "source": "render_yaml",
  "render_yaml_path": "<relative file path>"
}
```

### 2c. Web Service Example

```yaml
- type: web_service
  name: my-api
  plan: standard
  region: oregon
  healthCheckPath: /health
  numInstances: 2
  envVars:
    - key: DATABASE_URL
      fromDatabase:
        name: my-db
        property: connectionString
    - key: SECRET_KEY
      sync: false
```

→

```json
{
  "service_id": "web:my-api",
  "service_type": "web_service",
  "name": "my-api",
  "plan": "standard",
  "region": "oregon",
  "config": {
    "health_check_path": "/health",
    "num_instances": 2,
    "env_var_keys": ["DATABASE_URL", "SECRET_KEY"]
  },
  "source": "render_yaml",
  "render_yaml_path": "render.yaml"
}
```

**Security:** Record variable KEYS ONLY from `envVars`. Redact all values — including
`fromDatabase`, `fromService`, `sync: false` (secrets), and literal value fields.

### 2d. Cron Job Example

```yaml
- type: cron_job
  name: nightly-cleanup
  plan: starter
  schedule: "0 2 * * *"
  startCommand: python cleanup.py
```

→

```json
{
  "service_id": "cron:nightly-cleanup",
  "service_type": "cron_job",
  "name": "nightly-cleanup",
  "plan": "starter",
  "region": null,
  "config": {
    "schedule": "0 2 * * *",
    "start_command": "python cleanup.py"
  },
  "source": "render_yaml",
  "render_yaml_path": "render.yaml"
}
```

### 2e. Postgres Example

```yaml
- type: postgres
  name: my-db
  plan: standard
  region: oregon
  postgresMajorVersion: "16"
  highAvailability: false
```

→

```json
{
  "service_id": "postgres:my-db",
  "service_type": "postgres",
  "name": "my-db",
  "plan": "standard",
  "region": "oregon",
  "config": {
    "postgres_major_version": "16",
    "high_availability": false
  },
  "source": "render_yaml",
  "render_yaml_path": "render.yaml"
}
```

### 2f. Key-Value (Redis) Example

```yaml
- type: key_value
  name: my-redis
  plan: starter
  region: oregon
  maxMemoryPolicy: allkeys-lru
```

→

```json
{
  "service_id": "redis:my-redis",
  "service_type": "key_value",
  "name": "my-redis",
  "plan": "starter",
  "region": "oregon",
  "config": {
    "max_memory_policy": "allkeys-lru"
  },
  "source": "render_yaml",
  "render_yaml_path": "render.yaml"
}
```

---

## Step 3: Output Contribution for Parent Orchestrator

The phase assembler (`discover-assemble.md`) owns the inventory's STRUCTURE. This fragment contributes:

- **Resources:** all render.yaml-sourced entries go into `resources[]`.
- **Confidence:** set `metadata.confidence` to `"full"` when render.yaml parsed successfully, or `"reduced"` if any parse errors occurred.
- **Discovery sources:** contribute `"render_yaml"` to `metadata.discovery_sources`.
- **`render_yaml_metadata`:** contribute the shape shown below.

```json
{
  "render_yaml_metadata": {
    "found": true,
    "path": "render.yaml",
    "service_count": 5,
    "out_of_scope_service_types": ["static_site"],
    "parse_warnings": []
  }
}
```

---

## Scope Boundary

**This sub-file covers render.yaml parsing ONLY.**

FORBIDDEN — Do NOT include ANY of:

- AWS service names, recommendations, or equivalents
- Migration strategies, phases, or timelines
- Terraform generation for AWS
- Cost estimates or comparisons
- Effort estimates
- Running CLI commands

**Your ONLY job: Extract Render service declarations from `render.yaml` and produce inventory entries. Nothing else.**

After generating the resource entries, the parent `discover.md` handles merging into the final inventory and updating phase status — do NOT update `.phase-status.json` from this sub-file.
