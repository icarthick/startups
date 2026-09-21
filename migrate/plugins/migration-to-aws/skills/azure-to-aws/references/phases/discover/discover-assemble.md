---
_assemble: discover
_of_phase: discover
_produces:
  - azure-resource-inventory.json
---

# Discover Phase: Assembler

Assemble fragment contributions into the final `azure-resource-inventory.json`, then update
`.phase-status.json`.

**Execute ALL steps in order.**

---

## Step 1: Build the Inventory Structure

Combine contributions from the `terraform` fragment into the standard inventory shape:

```json
{
  "metadata": {
    "discovery_timestamp": "<ISO 8601 timestamp>",
    "total_resources_discovered": "<count of resources[]>",
    "discovery_sources": ["terraform"],
    "confidence": "full|reduced",
    "confidence_note": "<reason if reduced, else null>"
  },
  "resource_groups": [
    {
      "name": "<rg name>",
      "location": "<azure region>"
    }
  ],
  "resources": [
    {
      "resource_id": "<generated>",
      "resource_type": "<type>",
      "resource_group": "<rg name>",
      "config": {},
      "mapping_status": "supported|detect_only|specialist_gate|unsupported_type",
      "source": "terraform",
      "tf_file": "<relative path>",
      "tf_resource_name": "<local name>"
    }
  ],
  "specialist_gates": [
    {
      "resource_id": "<id>",
      "resource_type": "<type>",
      "reason": "AKS requires specialist engagement (EKS migration complexity)|Cosmos DB has a complex multi-API surface"
    }
  ],
  "terraform_metadata": {
    "found": true,
    "tf_files_scanned": 0,
    "resource_types_extracted": [],
    "parse_warnings": []
  }
}
```

- Set `metadata.total_resources_discovered` to `resources[].length`.
- Move any resource with `mapping_status: "specialist_gate"` or `detect_only` to
  `specialist_gates[]` as well (keep in `resources[]` for completeness).
- Set `confidence: "reduced"` if `terraform_metadata.parse_warnings` is non-empty.

---

## Step 2: Validation Checklist

Before writing the file, verify:

1. `metadata.discovery_timestamp` is a valid ISO 8601 string.
2. `metadata.total_resources_discovered` equals `resources[].length`.
3. Every entry in `resources[]` has `resource_id`, `resource_type`, and `config`.
4. No entry has forbidden clustering fields (`cluster_id`, `edges`, `dependencies`,
   `must_migrate_together`).
5. No secret values appear in any `config` field (app_setting_values, connection strings,
   passwords). Keys are allowed; values are not.

If any check fails: halt and report the specific failure. Do not write a partial file.

---

## Step 3: Write `azure-resource-inventory.json`

Write the assembled structure to `$MIGRATION_DIR/azure-resource-inventory.json`.

---

## Step 4: Update `.phase-status.json`

Set `phases.discover` to `"completed"` and `current_phase` to `"clarify"` in
`$MIGRATION_DIR/.phase-status.json`.

Emit: `HANDOFF_OK | phase=discover`
