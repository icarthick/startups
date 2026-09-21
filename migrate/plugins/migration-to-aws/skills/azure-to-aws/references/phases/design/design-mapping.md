---
_fragment: mapping-engine
_of_phase: design
_contributes:
  - aws-design.json (services[], deferred[], vpc_design)
---

# Design Phase: Azure → AWS Mapping Engine

Deterministic mapping from `azurerm_*` resource types to AWS equivalents. Process every
entry in `azure-resource-inventory.json` resources[] in input order. Use the tables below
as lookup — do not infer or guess mappings outside these tables.

---

## Primary Mapping Table

| `azurerm` resource type                               | AWS target                                 | Notes                                                                             |
| ----------------------------------------------------- | ------------------------------------------ | --------------------------------------------------------------------------------- |
| `azurerm_linux_web_app` + `azurerm_service_plan`      | ECS Fargate (default) or Elastic Beanstalk | Per `preferences.design_constraints.compute_target`                               |
| `azurerm_container_app`                               | ECS Fargate                                | Container-native, maps directly                                                   |
| `azurerm_container_app_environment`                   | (absorbed into ECS cluster config)         | No standalone AWS resource                                                        |
| `azurerm_postgresql_flexible_server`                  | Amazon RDS for PostgreSQL                  | Aurora PostgreSQL opt-in via clarify                                              |
| `azurerm_sql_server` + `azurerm_sql_database`         | Amazon RDS for SQL Server                  | Specialist gate for non-trivial schema                                            |
| `azurerm_storage_account` (blob/general-purpose)      | Amazon S3                                  | One bucket per storage account                                                    |
| `azurerm_storage_account` (file share)                | Amazon EFS                                 | detect-only in v1; note in deferred                                               |
| `azurerm_key_vault`                                   | AWS Secrets Manager + AWS KMS              | Secrets → Secrets Manager, keys → KMS CMK                                         |
| `azurerm_key_vault_secret`                            | (absorbed into Secrets Manager entry)      | Parent key vault drives the mapping                                               |
| `azurerm_function_app` / `azurerm_linux_function_app` | AWS Lambda                                 | Consumption plan → Lambda; App Service plan → Lambda with provisioned concurrency |
| `azurerm_redis_cache`                                 | Amazon ElastiCache for Redis               | SKU mapping table below                                                           |
| `azurerm_virtual_network`                             | Amazon VPC                                 | One VPC per virtual network                                                       |
| `azurerm_subnet`                                      | VPC Subnets                                | Public/private split driven by subnet naming/usage                                |
| `azurerm_resource_group`                              | (absorbed into VPC/tagging)                | Maps to AWS resource tagging + grouping, no standalone resource                   |
| `azurerm_kubernetes_cluster`                          | Amazon EKS                                 | **detect-only in v1** — surface specialist gate                                   |
| `azurerm_cosmosdb_account`                            | **Specialist gate — defer**                | Multi-API surface; no automated mapping                                           |
| `azurerm_windows_web_app`                             | ECS Fargate (Windows containers)           | **detect-only in v1** — note in deferred                                          |

---

## Compute Mapping Details

### Web Apps → ECS Fargate (default)

Read `preferences.design_constraints.compute_target.default`:

**ECS Fargate path (`ecs-fargate`):**

| `azurerm_service_plan` SKU    | Fargate CPU (units) | Fargate Memory (MiB) | Notes                 |
| ----------------------------- | ------------------- | -------------------- | --------------------- |
| B1, B2 (Basic)                | 256                 | 512                  | Dev tier              |
| S1, S2 (Standard)             | 512                 | 1024                 | Standard tier         |
| P1v2, P1v3 (Premium)          | 1024                | 2048                 | Premium tier          |
| P2v2, P2v3                    | 2048                | 4096                 | Premium large         |
| P3v2, P3v3                    | 4096                | 8192                 | Premium xlarge        |
| Y1 (Consumption / serverless) | 256                 | 512                  | Map to Lambda instead |
| Unknown / absent              | 256                 | 512                  | Default dev sizing    |

Set `aws_service: "Fargate"` and `aws_config.task_definition` with the CPU/memory values.

**Elastic Beanstalk path (`elastic_beanstalk`):**

Map `azurerm_service_plan` SKU to EC2 instance type:

| `azurerm_service_plan` SKU | EC2 instance type | Notes              |
| -------------------------- | ----------------- | ------------------ |
| B1, B2 (Basic)             | t3.micro          | Dev tier           |
| S1, S2 (Standard)          | t3.small          | Standard tier      |
| P1v2, P1v3                 | t3.medium         | Premium tier       |
| P2v2, P2v3                 | t3.large          | Premium large      |
| P3v2, P3v3                 | t3.xlarge         | Premium xlarge     |
| Unknown / absent           | t3.micro          | Default dev sizing |

Set `aws_service: "ElasticBeanstalk"` and `aws_config.instance_type`.

**Y1 (Consumption) plans:** always map to Lambda regardless of compute_target preference.

---

## Database Mapping Details

### `azurerm_postgresql_flexible_server` → RDS PostgreSQL

| Azure SKU prefix         | RDS instance class | Notes                   |
| ------------------------ | ------------------ | ----------------------- |
| `B_Standard` (Burstable) | db.t4g.micro       | Dev tier                |
| `D2s`, `GP_Standard_D2s` | db.t3.small        | General purpose 2 vCPU  |
| `D4s`, `GP_Standard_D4s` | db.t3.medium       | General purpose 4 vCPU  |
| `D8s`, `GP_Standard_D8s` | db.t3.large        | General purpose 8 vCPU  |
| `E2s`, `MO_Standard_E2s` | db.r6g.large       | Memory optimized 2 vCPU |
| `E4s`, `MO_Standard_E4s` | db.r6g.xlarge      | Memory optimized 4 vCPU |
| Unknown / absent         | db.t4g.micro       | Default dev sizing      |

Set `aws_config.engine: "postgres"`, `aws_config.engine_version` to the Azure
`engine_version` if set (e.g. `"14"`, `"15"`), else `"15"`. Set `aws_config.multi_az`
from `preferences.data.database_ha`.

### `azurerm_sql_server` / `azurerm_sql_database` → RDS SQL Server

Set `aws_service: "RDS"`, `aws_config.engine: "sqlserver-se"` (Standard Edition default).
Use `db.t3.medium` as default instance class. Note in `trade_offs` that non-trivial schemas
may require a specialist engagement.

---

## Storage Mapping Details

### `azurerm_storage_account` → S3 or EFS

Detect the storage account kind:

- `BlobStorage`, `BlockBlobStorage`, `StorageV2` with no file shares in inventory → S3.
- `Storage`, `StorageV2` with `azurerm_storage_share` in same account → EFS (detect-only
  in v1: add to `deferred[]` with reason "File share → EFS mapping is detect-only in v1").

For S3: set `aws_service: "S3"`, `aws_config.bucket_name: "<storage_account_name>"` (note:
S3 bucket names are globally unique; instruct user to verify availability).

---

## Secrets Mapping

### `azurerm_key_vault` → Secrets Manager + KMS

Map each Key Vault to:

1. An **AWS Secrets Manager** namespace (for secrets).
2. An **AWS KMS Customer Managed Key** (for encryption keys and certificates).

Set `aws_service: "SecretsManager"` as the primary, with `aws_config.kms_key: true` to
indicate a companion KMS CMK.

---

## Functions Mapping

### `azurerm_function_app` / `azurerm_linux_function_app` → Lambda

- Consumption plan (`Y1` service plan or no plan): `aws_service: "Lambda"`,
  `aws_config.invocation_mode: "event_driven"`.
- App Service / Premium plan: `aws_service: "Lambda"`,
  `aws_config.provisioned_concurrency: true`.

---

## Redis Mapping

### `azurerm_redis_cache` → ElastiCache for Redis

| Azure `sku_name` | Azure `capacity` | ElastiCache node type | Notes              |
| ---------------- | ---------------- | --------------------- | ------------------ |
| Basic            | 0                | cache.t4g.micro       | Dev tier           |
| Basic            | 1                | cache.t4g.small       | Small              |
| Standard         | 1                | cache.t4g.medium      | Standard           |
| Standard         | 2                | cache.r6g.large       | Standard large     |
| Premium          | 1                | cache.r6g.xlarge      | Premium            |
| Premium          | 2                | cache.r6g.2xlarge     | Premium large      |
| Unknown          | -                | cache.t4g.micro       | Default dev sizing |

---

## Networking Mapping

### `azurerm_virtual_network` → VPC

Map each virtual network to one VPC. Preserve the `address_space` CIDR if it does not
conflict with AWS reserved ranges; otherwise suggest `10.0.0.0/16` as default.

### `azurerm_subnet` → VPC Subnets

Preserve subnet CIDRs. Classify:

- Subnets named `*public*`, `*dmz*`, `*frontend*` → public subnet.
- All others → private subnet.
- Apply across all AZs per `preferences.global.high_availability`.

---

## Detect-Only and Specialist Gates

Resources with `mapping_status: "detect_only"` or `"specialist_gate"` are recorded in
`deferred[]`:

- `azurerm_kubernetes_cluster` → `reason: "AKS → EKS migration requires specialist
  engagement (node pool sizing, networking, workload migration)"`, `recommendation:
  "Engage a Kubernetes migration specialist; consider Amazon EKS Managed Upgrade."`.
- `azurerm_cosmosdb_account` → `reason: "Cosmos DB has a complex multi-API surface
  (SQL, MongoDB, Cassandra, Gremlin, Table) — no single automated mapping."`,
  `recommendation: "Identify the active API; map to DynamoDB (NoSQL), DocumentDB
  (MongoDB), or Keyspaces (Cassandra) accordingly."`.
- `azurerm_windows_web_app` → `reason: "Windows web apps are detect-only in v1."`,
  `recommendation: "Target ECS Fargate with Windows containers or discuss re-platform
  to .NET on Linux with the application team."`.
- `azurerm_storage_share` / EFS → `reason: "Azure File Share → EFS is detect-only in v1."`,
  `recommendation: "Evaluate Amazon EFS for lift-and-shift or Amazon S3 for
  cloud-native re-platform."`.

---

## Per-Resource Output Contract

For each mapped resource, contribute:

```json
{
  "service_id": "<source_resource_id>-aws",
  "source_resource_id": "<azure resource_id>",
  "azure_resource_type": "<azurerm_*>",
  "aws_service": "<ECS|Fargate|ElasticBeanstalk|RDS|S3|SecretsManager|Lambda|ElastiCache|VPC|EFS>",
  "confidence": "high|medium|low",
  "aws_config": {},
  "trade_offs": "<brief prose: what changes, what to watch>",
  "migration_notes": "<optional: key steps or caveats>"
}
```

After generating entries, pass to `design-assemble.md`. Do NOT update `.phase-status.json`
from this fragment.
