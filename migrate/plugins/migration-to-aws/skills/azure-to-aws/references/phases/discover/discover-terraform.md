---
_fragment: terraform
_of_phase: discover
_contributes:
  - azure-resource-inventory.json (resource entries, metadata, terraform_metadata sections)
---

# Discover Phase: Terraform Discovery

> Self-contained Terraform discovery sub-file. Scans `.tf` files for `azurerm_*` resource
> types, extracts resource configuration attributes, maps them to the inventory format.
> If no `.tf` files with `azurerm_*` resources are found, exits cleanly with no output.

**Execute ALL steps in order. Do not skip or optimize.**

---

## Step 0: Scan for `.tf` Files with `azurerm_*` Resources

Recursively scan the workspace directory for Terraform files containing Azure resources.

### 0a. File Discovery

Glob pattern: `**/*.tf`

Exclude directories:

- `.terraform/` (provider binaries and cached modules)
- `node_modules/`
- `.git/`

### 0b. Content Filtering

For each discovered `.tf` file, scan file contents for resource blocks matching:

```
resource "azurerm_*" "..." {
```

**Target resource types (v1):**

- `azurerm_linux_web_app`
- `azurerm_windows_web_app`
- `azurerm_service_plan`
- `azurerm_container_app`
- `azurerm_container_app_environment`
- `azurerm_postgresql_flexible_server`
- `azurerm_sql_server`
- `azurerm_sql_database`
- `azurerm_storage_account`
- `azurerm_storage_blob`
- `azurerm_storage_share`
- `azurerm_key_vault`
- `azurerm_key_vault_secret`
- `azurerm_function_app`
- `azurerm_linux_function_app`
- `azurerm_redis_cache`
- `azurerm_virtual_network`
- `azurerm_subnet`
- `azurerm_kubernetes_cluster`
- `azurerm_cosmosdb_account`
- `azurerm_resource_group`

All other `azurerm_*` types: record type and name only, set `mapping_status:
"unsupported_type"`.

---

## Step 1: Extract Resources from Terraform

For each `.tf` file containing `azurerm_*` resources, parse the Terraform HCL to extract
resource blocks. Process files in alphabetical order for deterministic output.

### 1a. HCL Block Extraction

For each `resource` block with an `azurerm_*` type, extract:

| Field              | Source                                           | Description                       |
| ------------------ | ------------------------------------------------ | --------------------------------- |
| `tf_resource_type` | Block type label (e.g., `azurerm_linux_web_app`) | The Terraform resource type       |
| `tf_resource_name` | Block name label (e.g., `"my-app"`)              | The Terraform resource local name |
| `tf_file`          | File path relative to workspace root             | Source file for traceability      |
| `attributes`       | All key-value pairs within the block             | Configuration attributes          |

### 1b. Resource Type Extraction Details

#### `azurerm_resource_group`

| Attribute  | Inventory Field | Required |
| ---------- | --------------- | -------- |
| `name`     | `name`          | Yes      |
| `location` | `location`      | Yes      |

#### `azurerm_linux_web_app` / `azurerm_windows_web_app`

| Attribute             | Inventory Field                | Required |
| --------------------- | ------------------------------ | -------- |
| `name`                | `name`                         | Yes      |
| `resource_group_name` | `resource_group`               | Yes      |
| `service_plan_id`     | `service_plan_ref`             | Yes      |
| `site_config`         | `site_config` (nested)         | No       |
| `app_settings`        | `app_setting_keys` (keys only) | No       |

**Security:** Record `app_settings` keys only. Never record values.

Windows web apps: set `os_type: "windows"` and `mapping_status: "detect_only"` (v1).

#### `azurerm_service_plan`

| Attribute             | Inventory Field  | Required |
| --------------------- | ---------------- | -------- |
| `name`                | `name`           | Yes      |
| `resource_group_name` | `resource_group` | Yes      |
| `sku_name`            | `sku`            | Yes      |
| `os_type`             | `os_type`        | Yes      |
| `worker_count`        | `worker_count`   | No       |

#### `azurerm_container_app`

| Attribute                      | Inventory Field                | Required |
| ------------------------------ | ------------------------------ | -------- |
| `name`                         | `name`                         | Yes      |
| `resource_group_name`          | `resource_group`               | Yes      |
| `container_app_environment_id` | `environment_ref`              | Yes      |
| `template`                     | `template` (nested CPU/memory) | No       |

#### `azurerm_postgresql_flexible_server`

| Attribute             | Inventory Field          | Required |
| --------------------- | ------------------------ | -------- |
| `name`                | `name`                   | Yes      |
| `resource_group_name` | `resource_group`         | Yes      |
| `sku_name`            | `sku`                    | Yes      |
| `storage_mb`          | `storage_mb`             | No       |
| `version`             | `engine_version`         | No       |
| `administrator_login` | `admin_login` (key only) | No       |
| `high_availability`   | `ha_enabled`             | No       |

#### `azurerm_sql_server` / `azurerm_sql_database`

| Attribute             | Inventory Field  | Required |
| --------------------- | ---------------- | -------- |
| `name`                | `name`           | Yes      |
| `resource_group_name` | `resource_group` | Yes      |
| `version` (server)    | `engine_version` | No       |
| `sku_name` (database) | `sku`            | No       |

#### `azurerm_storage_account`

| Attribute                  | Inventory Field  | Required |
| -------------------------- | ---------------- | -------- |
| `name`                     | `name`           | Yes      |
| `resource_group_name`      | `resource_group` | Yes      |
| `account_tier`             | `account_tier`   | Yes      |
| `account_replication_type` | `replication`    | Yes      |
| `account_kind`             | `account_kind`   | No       |

#### `azurerm_key_vault`

| Attribute                   | Inventory Field  | Required |
| --------------------------- | ---------------- | -------- |
| `name`                      | `name`           | Yes      |
| `resource_group_name`       | `resource_group` | Yes      |
| `sku_name`                  | `sku`            | Yes      |
| `enable_rbac_authorization` | `rbac_enabled`   | No       |

#### `azurerm_function_app` / `azurerm_linux_function_app`

| Attribute              | Inventory Field       | Required |
| ---------------------- | --------------------- | -------- |
| `name`                 | `name`                | Yes      |
| `resource_group_name`  | `resource_group`      | Yes      |
| `service_plan_id`      | `service_plan_ref`    | No       |
| `storage_account_name` | `storage_account_ref` | No       |

#### `azurerm_redis_cache`

| Attribute             | Inventory Field  | Required |
| --------------------- | ---------------- | -------- |
| `name`                | `name`           | Yes      |
| `resource_group_name` | `resource_group` | Yes      |
| `sku_name`            | `sku`            | Yes      |
| `family`              | `family`         | Yes      |
| `capacity`            | `capacity`       | Yes      |

#### `azurerm_virtual_network`

| Attribute             | Inventory Field  | Required |
| --------------------- | ---------------- | -------- |
| `name`                | `name`           | Yes      |
| `resource_group_name` | `resource_group` | Yes      |
| `address_space`       | `address_space`  | Yes      |

#### `azurerm_subnet`

| Attribute              | Inventory Field    | Required |
| ---------------------- | ------------------ | -------- |
| `name`                 | `name`             | Yes      |
| `resource_group_name`  | `resource_group`   | Yes      |
| `virtual_network_name` | `vnet_ref`         | Yes      |
| `address_prefixes`     | `address_prefixes` | Yes      |

#### `azurerm_kubernetes_cluster`

Set `mapping_status: "detect_only"` and `specialist_gate: true`. Record name, location,
kubernetes_version, default_node_pool sku/count if present.

#### `azurerm_cosmosdb_account`

Set `mapping_status: "specialist_gate"` and `specialist_gate: true`. Record name, kind,
capabilities if present. Do not attempt mapping.

---

## Step 2: Map Resources to Inventory Format

### 2a. Resource ID Generation

| Terraform Type                       | Inventory `resource_id` Format | Inventory `resource_type`   |
| ------------------------------------ | ------------------------------ | --------------------------- |
| `azurerm_resource_group`             | `rg:{name}`                    | `resource_group`            |
| `azurerm_linux_web_app`              | `webapp:{name}`                | `web_app`                   |
| `azurerm_windows_web_app`            | `webapp:{name}`                | `web_app`                   |
| `azurerm_service_plan`               | `serviceplan:{name}`           | `service_plan`              |
| `azurerm_container_app`              | `containerapp:{name}`          | `container_app`             |
| `azurerm_container_app_environment`  | `containerenv:{name}`          | `container_app_environment` |
| `azurerm_postgresql_flexible_server` | `postgres:{name}`              | `postgresql`                |
| `azurerm_sql_server`                 | `sqlserver:{name}`             | `sql_server`                |
| `azurerm_sql_database`               | `sqldb:{server_ref}:{name}`    | `sql_database`              |
| `azurerm_storage_account`            | `storage:{name}`               | `storage_account`           |
| `azurerm_key_vault`                  | `keyvault:{name}`              | `key_vault`                 |
| `azurerm_function_app`               | `func:{name}`                  | `function_app`              |
| `azurerm_linux_function_app`         | `func:{name}`                  | `function_app`              |
| `azurerm_redis_cache`                | `redis:{name}`                 | `redis_cache`               |
| `azurerm_virtual_network`            | `vnet:{name}`                  | `virtual_network`           |
| `azurerm_subnet`                     | `subnet:{vnet_ref}:{name}`     | `subnet`                    |
| `azurerm_kubernetes_cluster`         | `aks:{name}`                   | `kubernetes_cluster`        |
| `azurerm_cosmosdb_account`           | `cosmos:{name}`                | `cosmosdb_account`          |

### 2b. Standard Resource Entry

```json
{
  "resource_id": "<generated per 2a>",
  "resource_type": "<mapped type>",
  "resource_group": "<resolved resource group name>",
  "config": { "<extracted attributes>" },
  "mapping_status": "supported|detect_only|specialist_gate|unsupported_type",
  "source": "terraform",
  "tf_file": "<relative file path>",
  "tf_resource_name": "<terraform local name>"
}
```

---

## Step 3: Output Contribution for Parent Orchestrator

- **Resources:** all Terraform-sourced entries go into `resources[]`.
- **Confidence:** set `metadata.confidence` to `"full"` when all Terraform files parsed
  successfully, or `"reduced"` if any parse errors occurred.
- **Discovery sources:** contribute `"terraform"` to `metadata.discovery_sources`.
- **`terraform_metadata`:**

```json
{
  "terraform_metadata": {
    "found": true,
    "tf_files_scanned": 3,
    "resource_types_extracted": ["azurerm_linux_web_app", "azurerm_postgresql_flexible_server"],
    "parse_warnings": []
  }
}
```

---

## Error Handling

| Error Category                   | Behavior                                     | Effect on Discovery                    |
| -------------------------------- | -------------------------------------------- | -------------------------------------- |
| HCL parse error in one file      | Log warning, skip malformed blocks, continue | Other files still processed            |
| No azurerm_* resources found     | Exit cleanly, contribute empty resources[]   | Phase precondition fails               |
| Unresolvable Terraform reference | Record `"unresolved:{ref}"`, continue        | Resource included with limited context |

**Key principle:** Partial results are always better than no results. Any parse failure
results in a warning and graceful skip for that block — do NOT halt discovery.

---

## Scope Boundary

**This sub-file covers azurerm Terraform resource extraction ONLY.**

FORBIDDEN — Do NOT include AWS service names, recommendations, migration strategies,
cost estimates, or Terraform generation for AWS.

After generating resource entries, the parent `discover.md` handles merging into the final
inventory — do NOT update `.phase-status.json` from this sub-file.
