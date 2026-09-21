# Azure Discovery Schema

Schema for `azure-resource-inventory.json`, produced by the Discover phase orchestrator
(`discover.md`).

**Convention**: Values shown as `X|Y` indicate allowed alternatives — use exactly one
value per field.

---

## azure-resource-inventory.json (Phase 1 output)

Complete inventory of discovered Azure resources. Uses a **flat resource model** — no
clustering, no dependency graphs.

```json
{
  "metadata": {
    "discovery_timestamp": "2026-09-21T10:00:00Z",
    "total_resources_discovered": 5,
    "discovery_sources": ["terraform"],
    "confidence": "full|reduced",
    "confidence_note": "Terraform had parse errors on some files (if reduced)"
  },
  "resource_groups": [
    {
      "name": "my-rg",
      "location": "eastus"
    }
  ],
  "resources": [
    {
      "resource_id": "webapp:my-web-app",
      "resource_type": "web_app",
      "resource_group": "my-rg",
      "config": {
        "name": "my-web-app",
        "service_plan_ref": "serviceplan:my-asp",
        "app_setting_keys": ["DATABASE_URL", "REDIS_URL"]
      },
      "mapping_status": "supported|detect_only|specialist_gate|unsupported_type",
      "source": "terraform",
      "tf_file": "main.tf",
      "tf_resource_name": "app"
    }
  ],
  "specialist_gates": [
    {
      "resource_id": "aks:my-cluster",
      "resource_type": "kubernetes_cluster",
      "reason": "AKS requires specialist engagement"
    }
  ],
  "terraform_metadata": {
    "found": true,
    "tf_files_scanned": 3,
    "resource_types_extracted": ["azurerm_linux_web_app", "azurerm_service_plan"],
    "parse_warnings": []
  }
}
```

### metadata

| Field                        | Type                    | Required | Description                     |
| ---------------------------- | ----------------------- | -------- | ------------------------------- |
| `discovery_timestamp`        | ISO 8601 string         | Yes      | When discovery ran              |
| `total_resources_discovered` | integer                 | Yes      | Must equal `resources[].length` |
| `discovery_sources`          | string[]                | Yes      | Always `["terraform"]` in v1    |
| `confidence`                 | `"full"` \| `"reduced"` | Yes      | Full = no parse errors          |
| `confidence_note`            | string \| null          | No       | Reason if reduced               |

### resource entry

| Field              | Type          | Required | Description                                                             |
| ------------------ | ------------- | -------- | ----------------------------------------------------------------------- |
| `resource_id`      | string        | Yes      | Stable identifier per 2a of discover-terraform.md                       |
| `resource_type`    | string        | Yes      | Normalized type (e.g. `web_app`, `postgresql`)                          |
| `resource_group`   | string        | Yes      | Azure resource group name                                               |
| `config`           | object        | Yes      | Resource-type-specific attributes                                       |
| `mapping_status`   | string        | Yes      | `supported` \| `detect_only` \| `specialist_gate` \| `unsupported_type` |
| `source`           | `"terraform"` | Yes      | Always `"terraform"` in v1                                              |
| `tf_file`          | string        | Yes      | Relative path to the .tf file                                           |
| `tf_resource_name` | string        | Yes      | Terraform local resource name                                           |

### Invariants

- No `cluster_id`, `creation_order_depth`, `edges`, `dependencies`, or
  `must_migrate_together` fields anywhere in the document.
- No secret VALUES in any `config` field — keys only.
- `metadata.total_resources_discovered == resources[].length`.
