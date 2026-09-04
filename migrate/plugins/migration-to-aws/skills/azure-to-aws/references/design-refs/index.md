# Canonical ARM type → design reference

Routing for pass 2. Every row is keyed by a **canonical `Microsoft.*` ARM type**, never
a Terraform type — `arm-type-canonicalization.md` has already translated by the time
Design runs.

> **Column note.** *Typical AWS target* is the usual rubric OUTCOME, not a promise and
> not a confidence label. Only types in `knowledge/design/fast-path-services.json` →
> `direct_mappings` get `deterministic`. Everything routed through this file is
> `inferred`, or `measured` when observed utilization backed the choice. See
> `fast-path.md` § Confidence vocabulary.

> **A type in this file has already failed the fast-path lookup.** Check
> `fast-path-services.json` FIRST — `skip_mappings`, then `specialist_gates`, then
> `direct_mappings`. A type that matched there never reaches this file. Types that
> appear in both are listed here anyway, with their fast-path disposition named in the
> Reference column, so this file can be read as the complete type inventory.

> **HALT if a Reference file named below is not on disk.** Emit `GATE_FAIL` naming the
> type and the missing file. Do **not** map the resource from your own knowledge of
> Azure and AWS. This is the same guard, for the same reason, as `discover-iac.md`
> Step 2: "no rubric needed" and "the rubric has not been written yet" are otherwise
> indistinguishable, and improvising past the second produces a mapping that satisfies
> every shape assertion, carries a confidence label it did not earn, and differs
> between two runs of the same estate.

## Compute

| Canonical ARM type                                      | Reference             | Typical AWS target                                                             |
| ------------------------------------------------------- | --------------------- | ------------------------------------------------------------------------------ |
| `Microsoft.Web/serverfarms`                             | `compute.md`          | Elastic Beanstalk (default), Fargate, or EKS — **this is the compute unit**     |
| `Microsoft.Web/sites`                                   | `compute.md`          | none of its own — fans IN to its plan (see `design-infra.md`)                   |
| `Microsoft.Web/sites` (`kind` contains `functionapp`)   | `compute.md`          | Lambda, or Fargate when the surrounding workload is containerized              |
| `Microsoft.Web/sites/slots`                             | fast-path: skip       | a blue-green note on the parent plan's mapping                                 |
| `Microsoft.Web/staticSites`                             | `compute.md`          | S3 + CloudFront, with Lambda + API Gateway for its managed functions           |
| `Microsoft.Compute/virtualMachines`                     | `compute.md`          | EC2 (MGN-based cutover). SQL Server images additionally hit a specialist gate   |
| `Microsoft.Compute/virtualMachineScaleSets`             | `compute.md`          | EC2 Auto Scaling group                                                         |
| `Microsoft.Compute/availabilitySets`                    | fast-path: skip       | multi-AZ spread on the members' ASG                                            |
| `Microsoft.ContainerService/managedClusters`            | fast-path: **direct** | EKS                                                                            |
| `Microsoft.ContainerService/managedClusters/agentPools` | fast-path: skip       | EKS node-group sizing on the parent                                            |
| `Microsoft.ContainerRegistry/registries`                | fast-path: **direct** | ECR                                                                            |
| `Microsoft.App/containerApps`                           | `compute.md`          | Fargate                                                                        |
| `Microsoft.App/managedEnvironments`                     | `compute.md`          | ECS cluster + VPC; usually a config source for its container apps              |

GPU and HPC VM series (ND / NC / NV / HB / HX) branch inside `compute.md` to
`gpu-hpc.md`. Windows and .NET workloads take the x86_64 path — see SKILL.md
§ Philosophy; Graviton is an offered optimization here, not the default.

## Data

| Canonical ARM type                                        | Reference             | Typical AWS target                                                  |
| --------------------------------------------------------- | --------------------- | ------------------------------------------------------------------- |
| `Microsoft.DBforPostgreSQL/flexibleServers`               | `database.md`         | RDS PostgreSQL or Aurora PostgreSQL — the availability answer selects the family |
| `Microsoft.DBforPostgreSQL/servers` (Single Server)       | `database.md`         | RDS PostgreSQL; note the source is retired on Azure                 |
| `Microsoft.DBforMySQL/flexibleServers`                    | `database.md`         | RDS MySQL or Aurora MySQL — availability selects the family         |
| `Microsoft.DBforMySQL/servers` (Single Server)            | `database.md`         | RDS MySQL                                                           |
| `Microsoft.Sql/servers`                                   | `database.md`         | the RDS instance that hosts its databases; often a config source    |
| `Microsoft.Sql/servers/databases`                         | `database.md`         | **RDS SQL Server** by default (owner decision 11.3)                 |
| `Microsoft.Sql/servers/elasticPools`                      | fast-path: **gate**   | `Deferred — specialist engagement`                                  |
| `Microsoft.Sql/managedInstances`                          | fast-path: **gate**   | `Deferred — specialist engagement`                                  |
| `Microsoft.DocumentDB/databaseAccounts` (Mongo/Cassandra/Gremlin/Table) | fast-path: **direct** | DocumentDB / Keyspaces / Neptune / DynamoDB by API      |
| `Microsoft.DocumentDB/databaseAccounts` (Core / SQL API)  | `database.md`         | DynamoDB — RU/s → WCU/RCU conversion, full depth                    |
| `Microsoft.Cache/Redis`                                   | fast-path: **direct** | ElastiCache Redis                                                   |
| `Microsoft.Cache/redisEnterprise`                         | `database.md`         | ElastiCache Redis, or MemoryDB; RediSearch/RedisJSON modules have no equivalent |

The availability selector (single-az / multi-az / multi-az-ha / multi-region) is a
**post-rubric override gate** in `database.md`, not a criterion — it forces RDS versus
Aurora regardless of rubric output, because availability is never inferable from IaC.

## Storage

| Canonical ARM type                                          | Reference             | Typical AWS target                       |
| ----------------------------------------------------------- | --------------------- | ---------------------------------------- |
| `Microsoft.Storage/storageAccounts`                         | fast-path: **direct** | S3 (blob surface)                        |
| `Microsoft.Storage/storageAccounts/blobServices/containers`  | fast-path: **direct** | S3                                       |
| `Microsoft.Storage/storageAccounts/fileServices/shares`      | fast-path: **direct** | FSx for Windows File Server (SMB) / EFS (NFS) |
| `Microsoft.Storage/storageAccounts/queueServices/queues`      | fast-path: **direct** | SQS                                      |
| `Microsoft.Storage/storageAccounts/tableServices/tables`      | fast-path: **direct** | DynamoDB                                 |
| `Microsoft.Compute/disks`                                    | fast-path: **direct** | EBS                                      |

`storage.md` carries the rubric for anything that reaches it — today only the share
row's protocol reasoning and the lifecycle/tiering notes. It exists because the
protocol discriminator has to be documented somewhere a reviewer can find it.

## Networking

| Canonical ARM type                          | Reference             | Typical AWS target                          |
| ------------------------------------------- | --------------------- | ------------------------------------------- |
| `Microsoft.Network/virtualNetworks`         | fast-path: **direct** | VPC                                         |
| `Microsoft.Network/virtualNetworks/subnets`  | fast-path: **direct** | VPC subnet                                  |
| `Microsoft.Network/networkSecurityGroups`   | fast-path: **direct** | Security Group (DENY rules need a NACL note) |
| `Microsoft.Network/dnsZones`                | fast-path: **direct** | Route 53 hosted zone                        |
| `Microsoft.Network/loadBalancers`           | `networking.md`       | NLB (or ALB when it fronts HTTP)            |
| `Microsoft.Network/applicationGateways`     | `networking.md`       | ALB, + AWS WAF when the WAF SKU is in use   |
| `Microsoft.Network/natGateways`             | `networking.md`       | NAT Gateway                                 |
| `Microsoft.Cdn/profiles`                    | `networking.md`       | CloudFront                                  |
| `Microsoft.Network/frontDoors` (deprecated) | `networking.md`       | CloudFront + AWS WAF                        |
| `Microsoft.ApiManagement/service`           | `networking.md`       | API Gateway                                 |
| `Microsoft.Network/networkInterfaces`       | fast-path: skip       | ENI, created by its owner                   |
| `Microsoft.Network/publicIPAddresses`       | fast-path: skip       | Elastic IP, managed by ALB/NAT              |
| `Microsoft.Network/privateEndpoints`        | fast-path: skip       | none — read for its edge                    |
| `Microsoft.Network/privateDnsZones`         | fast-path: skip       | implicit in the VPC design                  |

`networking.md` also carries the "free on AWS" findings — cross-AZ patterns, VPC
peering versus Azure's paid VNet peering — which are report content, not mappings.

## Messaging

| Canonical ARM type                        | Reference             | Typical AWS target                                     |
| ----------------------------------------- | --------------------- | ------------------------------------------------------ |
| `Microsoft.ServiceBus/namespaces`         | `messaging.md`        | SQS + SNS, or Amazon MQ when AMQP 1.0 is required      |
| `Microsoft.ServiceBus/namespaces/queues`  | `messaging.md`        | SQS                                                    |
| `Microsoft.ServiceBus/namespaces/topics`  | `messaging.md`        | SNS, or EventBridge for content-based routing          |
| `Microsoft.EventHub/namespaces`           | fast-path: **direct** | MSK when `kafka_enabled`, else Kinesis Data Streams    |
| `Microsoft.EventHub/namespaces/eventhubs` | `messaging.md`        | a topic or stream inside the parent's target           |
| `Microsoft.SignalRService/SignalR`        | `messaging.md`        | API Gateway WebSocket APIs, or AppSync subscriptions   |

Event Hubs is protocol-only by owner decision 11.4 and carries no throughput
threshold, which is why it is a fast-path row rather than a rubric row.

## Identity and secrets

| Canonical ARM type                                 | Reference             | Typical AWS target                    |
| -------------------------------------------------- | --------------------- | ------------------------------------- |
| `Microsoft.KeyVault/vaults`                        | fast-path: **direct** | Secrets Manager (+ KMS for keys, ACM for certificates) |
| `Microsoft.KeyVault/vaults/secrets`                | fast-path: skip       | names feed the parent vault           |
| `Microsoft.ManagedIdentity/userAssignedIdentities` | fast-path: **direct** | IAM Role                              |
| `Microsoft.Authorization/roleAssignments`          | fast-path: skip       | IAM policy, authored not translated   |
| `Microsoft.Authorization/roleDefinitions`          | fast-path: skip       | IAM policy                            |

Human identity — Entra ID tenants, users, groups, app registrations — is **not** a
resource mapping. It is `identity.md`, reached from Clarify category J, and it defaults
to a fresh IAM Identity Center re-invite rather than an Entra ID federation.

## AI

| Canonical ARM type                                     | Reference                                    | Typical AWS target |
| ------------------------------------------------------ | -------------------------------------------- | ------------------ |
| `Microsoft.CognitiveServices/accounts` (`kind: OpenAI`) | `vendored/ai/ai-openai-to-bedrock.md`        | Bedrock            |
| `Microsoft.CognitiveServices/accounts` (other kinds)   | `ai.md`                                      | Textract, Rekognition, Comprehend, Transcribe by capability |
| `Microsoft.CognitiveServices/accounts/deployments`     | `vendored/ai/ai-openai-to-bedrock.md`        | a config source — the deployed model name is the mapping input |

Azure OpenAI has no ARM provider of its own; `kind` is the only signal. The model
catalogue and the Bedrock mapping do not change based on which endpoint served the
calls, which is why this routes to the same shared guide as an OpenAI-direct workload.

## Analytics

| Canonical ARM type                     | Reference           | Typical AWS target                       |
| -------------------------------------- | ------------------- | ---------------------------------------- |
| `Microsoft.Search/searchServices`      | `analytics.md`      | Amazon OpenSearch Service                |
| `Microsoft.Databricks/workspaces`      | `analytics.md`      | Databricks on AWS (preferred) or EMR     |
| `Microsoft.Synapse/workspaces`         | fast-path: **gate** | `Deferred — specialist engagement`       |
| `Microsoft.DataFactory/factories`      | fast-path: **gate** | `Deferred — specialist engagement`       |

## Observability

Every `Microsoft.Insights/*` type and `Microsoft.OperationalInsights/workspaces` is a
**Skip Mapping** with a CloudWatch fallback note (owner decision 11.6). They are still
inventoried and translated — a resource absent from the inventory cannot be reported as
skipped, and Application Insights carries an `application_type` and a workspace link the
report should mention. There is no target and no import path for retained telemetry.

## Not in this file

| Canonical ARM type                    | Disposition                                             |
| ------------------------------------- | ------------------------------------------------------- |
| `Microsoft.Resources/resourceGroups`  | fast-path: skip — AWS account structure and tags        |
| `Microsoft.Resources/deployments`     | fast-path: skip — deployment history, not infrastructure |
| `Microsoft.Web/certificates`          | fast-path: skip — ACM issues for the target's hostnames  |

A canonical type that appears in **neither** this file nor
`fast-path-services.json` falls to the unknown-type policy in
`phases/design/design-infra.md`. That policy is deliberately split: benign unknowns warn
and continue, cost-bearing unknowns STOP. Do not add a speculative row here to avoid a
STOP — the STOP is the signal that the type needs filing.
