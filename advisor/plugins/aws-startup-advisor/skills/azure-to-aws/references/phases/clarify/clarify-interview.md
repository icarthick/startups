---
_fragment: interview
_of_phase: clarify
_contributes:
  - preferences.json (raw answered values, pre-assembly)
---

# Clarify Phase: Interview

Adaptive question set for Azure-to-AWS Terraform migrations. Present questions in two
batches (≤6 per batch). Interpret each answer immediately; use the Default from the table
if the user skips or says "use defaults".

---

## Prior-Run Check

Before presenting questions, check `$MIGRATION_DIR/.phase-status.json`:

- If `phases.clarify == "completed"` and `preferences.json` exists → load it, summarize
  existing preferences, and ask: "Would you like to update any preferences? (Y/N)"
  - If N: skip to clarify-assemble.md with existing data.
  - If Y: present the full question set.

---

## Batch 1: Core Requirements (present together)

**Q1. Target AWS region**

- Prompt: "Which AWS region should we target for the migration? (e.g. us-east-1,
  eu-west-1)"
- Default: `us-east-1`
- Field: `global.target_region`

**Q2. Compute target for web apps / container apps**

- Prompt: "For web apps and container apps (`azurerm_linux_web_app`, `azurerm_container_app`),
  which AWS compute target do you prefer? [A] ECS Fargate (default — containers, flexible
  scaling) [B] Elastic Beanstalk (managed platform, simpler ops)"
- Default: `ecs-fargate`
- Field: `design_constraints.compute_target`
- Values: `ecs-fargate` | `elastic_beanstalk`

**Q3. High availability**

- Prompt: "Should the AWS design use multi-AZ / high-availability configuration?
  [A] Yes — multi-AZ (production-grade) [B] No — single-AZ (development/cost-optimised)"
- Default: `false`
- Field: `global.high_availability`

**Q4. Database — HA / Multi-AZ** (only if inventory has postgresql or sql_database)

- Prompt: "For databases, should we enable Multi-AZ standby replicas on RDS?"
- Default: `false`
- Field: `data.database_ha`

**Q5. Existing VPC**

- Prompt: "Do you have an existing AWS VPC to deploy into, or should we create a new one?
  [A] Create new VPC (default) [B] Use existing VPC (provide VPC ID)"
- Default: `new_vpc`
- Field: `network.vpc_mode`
- If existing: capture `network.existing_vpc_id`

---

## Batch 2: Advanced Options (present together)

**Q6. Azure region → AWS region mapping**

- Prompt: "Your Terraform uses location `<detected_locations>`. Should we map all resources
  to `<target_region>`, or do you need specific regions for specific resource groups?"
- Default: map all to `global.target_region`
- Field: `global.region_map` (object: azure_location → aws_region, or `null` for uniform)

**Q7. IaC output structure**

- Prompt: "How should the generated AWS Terraform be structured?
  [A] Single flat module (default — simpler) [B] Separate modules per service domain"
- Default: `flat`
- Field: `generate.tf_structure`
- Values: `flat` | `modular`

**Q8. Storage: Blob → S3 transfer notes**

- Prompt: "For Azure Blob Storage accounts, should we include S3 data-transfer guidance
  (AzCopy → AWS CLI sync commands) in the migration guide? [A] Yes (default) [B] No"
- Default: `true`
- Field: `generate.include_storage_transfer_guide`

---

## Defaults Table

| Field                                     | Default                       |
| ----------------------------------------- | ----------------------------- |
| `global.target_region`                    | `us-east-1`                   |
| `design_constraints.compute_target`       | `ecs-fargate`                 |
| `global.high_availability`                | `false`                       |
| `data.database_ha`                        | `false`                       |
| `network.vpc_mode`                        | `new_vpc`                     |
| `network.existing_vpc_id`                 | `null`                        |
| `global.region_map`                       | `null` (all to target_region) |
| `generate.tf_structure`                   | `flat`                        |
| `generate.include_storage_transfer_guide` | `true`                        |

---

## Answer Interpretation Rules

- `ecs-fargate` or `fargate` or `A` for Q2 → `ecs-fargate`
- `elastic_beanstalk` or `beanstalk` or `eb` or `B` for Q2 → `elastic_beanstalk`
- `yes`, `y`, `true`, `1` → `true` for boolean fields
- `no`, `n`, `false`, `0` → `false` for boolean fields
- If user provides an unrecognized value: re-ask once, then apply the default.

Pass raw interpreted values to `clarify-assemble.md` for final assembly.
