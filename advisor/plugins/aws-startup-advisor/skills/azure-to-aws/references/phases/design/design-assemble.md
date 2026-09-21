---
_assemble: design
_of_phase: design
_produces:
  - aws-design.json
---

# Design Phase: Assembler

Assemble fragment contributions into the final `aws-design.json`, then update
`.phase-status.json`.

---

## Step 1: Build the Design Structure

```json
{
  "phase": "design",
  "timestamp": "<ISO 8601>",
  "metadata": {
    "total_services": "<services[].length>",
    "total_deferred": "<deferred[].length>",
    "compute_target": "<preferences.design_constraints.compute_target.default>",
    "target_region": "<preferences.global.target_region>"
  },
  "services": [],
  "deferred": [],
  "vpc_design": {
    "mode": "new_vpc|existing_vpc",
    "cidr": "<derived from azure VNet or default 10.0.0.0/16>",
    "existing_vpc_id": "<null or vpc-id>",
    "subnets": [
      {
        "name": "<subnet name>",
        "cidr": "<cidr>",
        "type": "public|private",
        "availability_zones": ["<az1>", "<az2>"]
      }
    ]
  },
  "warnings": []
}
```

- Set `metadata.total_services` to `services[].length`.
- Set `vpc_design.mode` from `preferences.network.vpc_mode`.
- If `preferences.global.high_availability == true`: create subnets across 2 AZs minimum.
- If `preferences.global.high_availability == false`: single AZ.

---

## Step 2: Validation Checklist

1. `phase == "design"` and `timestamp` is a valid ISO 8601 string.
2. `services[]` is present (may be empty only if ALL resources were deferred).
3. Every `services[]` entry has `service_id`, `source_resource_id`, `azure_resource_type`,
   `aws_service`, `confidence`, and `aws_config`.
4. Every `deferred[]` entry has `resource_id`, `azure_resource_type`, `reason`, and
   `recommendation`.
5. `vpc_design` is present with a valid `mode`.
6. `metadata.total_services == services[].length`.
7. No `azurerm_windows_web_app`, `azurerm_kubernetes_cluster`, or `azurerm_cosmosdb_account`
   appears in `services[]` as a fully-mapped primary service.

If any check fails: halt and report the specific failure.

---

## Step 3: Write aws-design.json

Write the assembled structure to `$MIGRATION_DIR/aws-design.json`.

---

## Step 4: Update .phase-status.json

Set `phases.design` to `"completed"` and `current_phase` to `"estimate"` in
`$MIGRATION_DIR/.phase-status.json`.

Emit: `HANDOFF_OK | phase=design`
