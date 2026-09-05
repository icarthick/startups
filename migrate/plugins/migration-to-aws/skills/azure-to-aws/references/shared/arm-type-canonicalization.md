# Canonical ARM type vocabulary (`azurerm_*` → `Microsoft.*`)

Every mapping table in this skill keys off an **ARM resource type string**
(`Microsoft.Web/sites`), never a Terraform type. Four of the five discovery sources
— Bicep, ARM templates, live `az`, and RDfA — speak ARM natively. Only Terraform
needs translating, and this file is that translation. It is applied inside
`discover-iac.md`, so nothing downstream ever sees an `azurerm_*` string.

gcp-to-aws did not face this because it had one IaC dialect and could key tables off
Terraform types directly.

## Rules

1. **The table is the authority, not inference.** Several ARM types are not derivable
   from the Terraform name, and two are actively misleading (see § Traps). If a type
   is absent from this table, `discover-iac.md` records it as an untranslated type in
   `warnings[]` and does NOT guess — a guessed type silently corrupts every
   downstream lookup, because the mapping tables will simply fail to match and the
   resource falls through to the unknown-type policy for the wrong reason.
2. **Casing is significant.** ARM type strings are compared case-sensitively by the
   mapping tables in this skill. Copy them verbatim from this file.
3. **Child types keep their full path.** `Microsoft.Sql/servers/databases` is three
   segments, and it is not interchangeable with `Microsoft.Sql/servers`.
4. **Deprecated provider names are listed alongside their replacements.** A real
   repository may carry either; both translate to the same ARM type.

## Traps

These are the rows where a plausible guess and the correct answer diverge. They are
the reason this file exists rather than relying on the pattern.

| Trap                                                                                                                                      | Wrong                             | Right                                    |
| ----------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------- | ---------------------------------------- |
| **Function apps are not their own type.** `Microsoft.Web/functionApps` does not exist. A function app is a `sites` resource with `kind` containing `functionapp`. | `Microsoft.Web/functionApps`      | `Microsoft.Web/sites`                    |
| **App Service Plan is `serverfarms`, all lowercase.** The camelCase `serverFarmId` is the *property* on a site that points at the plan — not the type name. | `Microsoft.Web/serverFarms`       | `Microsoft.Web/serverfarms`              |
| **Redis carries a capital R.** Unlike every neighbouring type, the resource segment is not lowerCamelCase.                                  | `Microsoft.Cache/redis`           | `Microsoft.Cache/Redis`                  |
| **Cosmos DB's provider is `DocumentDB`.** The product was renamed; the ARM provider never was.                                             | `Microsoft.CosmosDB/accounts`     | `Microsoft.DocumentDB/databaseAccounts`  |
| **Azure OpenAI has no provider of its own.** It is a Cognitive Services account whose `kind` is `OpenAI`.                                   | `Microsoft.OpenAI/accounts`       | `Microsoft.CognitiveServices/accounts`   |
| **A resource group's own ID has no `/providers/` segment.** See § Reconstructing `azure_id`.                                                | `.../providers/Microsoft.Resources/resourceGroups/rg` | `/subscriptions/<sub>/resourceGroups/rg` |

`kind` is therefore load-bearing, not decoration: it is the only thing separating a
web app from a function app, and a Cognitive Services account from Azure OpenAI.
`discover-iac.md` must carry it into `config.kind` for every `Microsoft.Web/sites`
and `Microsoft.CognitiveServices/accounts` entry.

## Compute

| Terraform type                                                                                                            | Canonical ARM type                                 |
| ------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------- |
| `azurerm_linux_web_app`, `azurerm_windows_web_app`, `azurerm_app_service` (deprecated)                                     | `Microsoft.Web/sites`                              |
| `azurerm_linux_function_app`, `azurerm_windows_function_app`, `azurerm_function_app` (deprecated)                           | `Microsoft.Web/sites` (`kind` contains `functionapp`) |
| `azurerm_linux_web_app_slot`, `azurerm_windows_web_app_slot`                                                               | `Microsoft.Web/sites/slots`                        |
| `azurerm_service_plan`, `azurerm_app_service_plan` (deprecated)                                                            | `Microsoft.Web/serverfarms`                        |
| `azurerm_static_site`                                                                                                     | `Microsoft.Web/staticSites`                        |
| `azurerm_linux_virtual_machine`, `azurerm_windows_virtual_machine`, `azurerm_virtual_machine` (deprecated)                  | `Microsoft.Compute/virtualMachines`                |
| `azurerm_linux_virtual_machine_scale_set`, `azurerm_windows_virtual_machine_scale_set`, `azurerm_orchestrated_virtual_machine_scale_set`, `azurerm_virtual_machine_scale_set` (deprecated) | `Microsoft.Compute/virtualMachineScaleSets` |
| `azurerm_managed_disk`                                                                                                    | `Microsoft.Compute/disks`                          |
| `azurerm_availability_set`                                                                                                | `Microsoft.Compute/availabilitySets`               |
| `azurerm_kubernetes_cluster`                                                                                              | `Microsoft.ContainerService/managedClusters`       |
| `azurerm_kubernetes_cluster_node_pool`                                                                                    | `Microsoft.ContainerService/managedClusters/agentPools` |
| `azurerm_container_registry`                                                                                              | `Microsoft.ContainerRegistry/registries`           |
| `azurerm_container_app`                                                                                                   | `Microsoft.App/containerApps`                      |
| `azurerm_container_app_environment`                                                                                       | `Microsoft.App/managedEnvironments`                |

## Data

| Terraform type                                                    | Canonical ARM type                            |
| ----------------------------------------------------------------- | --------------------------------------------- |
| `azurerm_postgresql_flexible_server`                              | `Microsoft.DBforPostgreSQL/flexibleServers`    |
| `azurerm_postgresql_server` (deprecated Single Server)            | `Microsoft.DBforPostgreSQL/servers`            |
| `azurerm_mysql_flexible_server`                                   | `Microsoft.DBforMySQL/flexibleServers`         |
| `azurerm_mysql_server` (deprecated Single Server)                 | `Microsoft.DBforMySQL/servers`                 |
| `azurerm_mssql_server`                                            | `Microsoft.Sql/servers`                        |
| `azurerm_mssql_database`                                          | `Microsoft.Sql/servers/databases`              |
| `azurerm_mssql_elasticpool`                                       | `Microsoft.Sql/servers/elasticPools`           |
| `azurerm_mssql_managed_instance`                                  | `Microsoft.Sql/managedInstances`               |
| `azurerm_cosmosdb_account`                                        | `Microsoft.DocumentDB/databaseAccounts`        |
| `azurerm_redis_cache`                                             | `Microsoft.Cache/Redis`                        |
| `azurerm_redis_enterprise_cluster`                                | `Microsoft.Cache/redisEnterprise`              |
| `azurerm_storage_account`                                         | `Microsoft.Storage/storageAccounts`            |
| `azurerm_storage_container`                                       | `Microsoft.Storage/storageAccounts/blobServices/containers` |
| `azurerm_storage_share`                                           | `Microsoft.Storage/storageAccounts/fileServices/shares` |
| `azurerm_storage_queue`                                           | `Microsoft.Storage/storageAccounts/queueServices/queues` |
| `azurerm_storage_table`                                           | `Microsoft.Storage/storageAccounts/tableServices/tables` |

Note that `azurerm_storage_share` is what makes the Azure Files → EFS-or-FSx routing
decision reachable: its `enabled_protocol` (`SMB` or `NFS`) is the discriminator, so
carry it into `config.enabled_protocol`.

## Networking

| Terraform type                    | Canonical ARM type                          |
| --------------------------------- | ------------------------------------------- |
| `azurerm_virtual_network`         | `Microsoft.Network/virtualNetworks`          |
| `azurerm_subnet`                  | `Microsoft.Network/virtualNetworks/subnets`  |
| `azurerm_network_security_group`  | `Microsoft.Network/networkSecurityGroups`    |
| `azurerm_network_interface`       | `Microsoft.Network/networkInterfaces`        |
| `azurerm_public_ip`               | `Microsoft.Network/publicIPAddresses`        |
| `azurerm_lb`                      | `Microsoft.Network/loadBalancers`            |
| `azurerm_application_gateway`     | `Microsoft.Network/applicationGateways`      |
| `azurerm_nat_gateway`             | `Microsoft.Network/natGateways`              |
| `azurerm_dns_zone`                | `Microsoft.Network/dnsZones`                 |
| `azurerm_private_dns_zone`        | `Microsoft.Network/privateDnsZones`          |
| `azurerm_private_endpoint`        | `Microsoft.Network/privateEndpoints`         |
| `azurerm_cdn_frontdoor_profile`   | `Microsoft.Cdn/profiles`                     |
| `azurerm_frontdoor` (deprecated)  | `Microsoft.Network/frontDoors`               |

## Identity, secrets, messaging

| Terraform type                       | Canonical ARM type                                    |
| ------------------------------------ | ----------------------------------------------------- |
| `azurerm_key_vault`                  | `Microsoft.KeyVault/vaults`                           |
| `azurerm_key_vault_secret`           | `Microsoft.KeyVault/vaults/secrets`                   |
| `azurerm_user_assigned_identity`     | `Microsoft.ManagedIdentity/userAssignedIdentities`    |
| `azurerm_role_assignment`            | `Microsoft.Authorization/roleAssignments`             |
| `azurerm_servicebus_namespace`       | `Microsoft.ServiceBus/namespaces`                     |
| `azurerm_servicebus_queue`           | `Microsoft.ServiceBus/namespaces/queues`              |
| `azurerm_servicebus_topic`           | `Microsoft.ServiceBus/namespaces/topics`              |
| `azurerm_eventhub_namespace`         | `Microsoft.EventHub/namespaces`                       |
| `azurerm_eventhub`                   | `Microsoft.EventHub/namespaces/eventhubs`             |
| `azurerm_api_management`             | `Microsoft.ApiManagement/service`                     |
| `azurerm_signalr_service`            | `Microsoft.SignalRService/SignalR`                    |

`azurerm_eventhub_namespace`'s `kafka_enabled` attribute is what the Event Hubs
rubric keys off (Kafka-protocol consumers → MSK, native AMQP/SDK → Kinesis), so carry
it into `config.kafka_enabled`.

## Observability, AI, analytics

| Terraform type                          | Canonical ARM type                                     |
| --------------------------------------- | ------------------------------------------------------ |
| `azurerm_application_insights`          | `Microsoft.Insights/components`                        |
| `azurerm_log_analytics_workspace`       | `Microsoft.OperationalInsights/workspaces`             |
| `azurerm_monitor_diagnostic_setting`    | `Microsoft.Insights/diagnosticSettings`                |
| `azurerm_monitor_action_group`          | `Microsoft.Insights/actionGroups`                      |
| `azurerm_monitor_metric_alert`          | `Microsoft.Insights/metricAlerts`                      |
| `azurerm_cognitive_account`             | `Microsoft.CognitiveServices/accounts` (`kind` = `OpenAI` for Azure OpenAI) |
| `azurerm_cognitive_deployment`          | `Microsoft.CognitiveServices/accounts/deployments`     |
| `azurerm_search_service`                | `Microsoft.Search/searchServices`                      |
| `azurerm_data_factory`                  | `Microsoft.DataFactory/factories`                      |
| `azurerm_synapse_workspace`             | `Microsoft.Synapse/workspaces`                         |
| `azurerm_databricks_workspace`          | `Microsoft.Databricks/workspaces`                      |

Everything in the observability block lands in Skip Mappings — observability is
re-established on the target rather than migrated, with a CloudWatch fallback note.
They are still translated and inventoried, because `Microsoft.Insights/components`
carries an `application_type` and a workspace link that the report should mention,
and because a resource absent from the inventory cannot be reported as skipped.

## Resource groups

| Terraform type            | Canonical ARM type                     |
| ------------------------- | -------------------------------------- |
| `azurerm_resource_group`  | `Microsoft.Resources/resourceGroups`   |

## Reconstructing `azure_id`

Terraform source does not contain ARM resource IDs, so Terraform-sourced entries
have theirs built. Every other source supplies it directly and must never have it
rebuilt.

**Standard form** — one provider segment, then type/name pairs:

```
/subscriptions/<subscriptionId>/resourceGroups/<rg>/providers/<Provider>/<type>/<name>
```

**Child resources** append further type/name pairs to the parent's path, and the
provider appears exactly once:

```
/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Sql/servers/<server>/databases/<db>
/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Web/sites/<site>/slots/<slot>
```

**A storage account's four sub-services are implicit singletons named `default`.** The
Terraform resource carries no name for that segment — there is only ever one — so the
literal `default` has to be supplied when the ID is built, and it is easy to omit
because nothing in the source hints at it:

```
/…/Microsoft.Storage/storageAccounts/<acct>/blobServices/default/containers/<name>
/…/Microsoft.Storage/storageAccounts/<acct>/fileServices/default/shares/<name>
/…/Microsoft.Storage/storageAccounts/<acct>/queueServices/default/queues/<name>
/…/Microsoft.Storage/storageAccounts/<acct>/tableServices/default/tables/<name>
```

The canonical **type** strings in the tables above deliberately omit `default` — a type
has no instance names in it. Only the **ID** carries it.

**A resource group is the exception** — its own ID carries no `/providers/` segment
at all, even though its canonical type is `Microsoft.Resources/resourceGroups`:

```
/subscriptions/<sub>/resourceGroups/<rg>
```

When the subscription id is not present in the Terraform (the common case — it comes
from the provider block, a variable, or the environment), use the literal placeholder
`<subscription-unknown>` in that position and set
`iac_metadata.subscription_id_source: "unresolved"` — **`iac_metadata`, not
`metadata`**. It belongs there because it is an IaC-specific fact: only Terraform needs
the ID reconstructed at all, so only the IaC section has anything to say about where the
subscription half came from. Do **not** invent a GUID: a fabricated
subscription id makes `azure_id` non-unique across two runs of the same repo and
breaks the drift comparison against a live capture, which is the one thing the ID
exists to support.
