# Extraction rules — Terraform (`azurerm_*`)

Loaded by `discover-iac.md` only when `.tf` files containing `azurerm_*` resources are
present. One of three per-dialect refs; the others are `extract-bicep.md` and
`extract-arm.md`. Each covers surface syntax only — the artifact contract is
`schema-discover-azure.md` and the canonical type vocabulary is
`arm-type-canonicalization.md`.

## Step 1: Find the files

Glob `**/*.tf` and `**/*.tf.json`, excluding `.terraform/`, `**/node_modules/`, and
any path under `$MIGRATION_DIR`. Read each file. A `.tf` file with no `azurerm_`
resource block contributes nothing and is not an error — many repos carry provider,
backend, and variable files with no resources at all.

**Do not read `terraform.tfstate`, `*.tfstate.backup`, or `.terraform/`.** State files
contain resolved attribute values including secrets that the configuration only
references. They are a credential-disclosure surface, and the declared configuration
is what this fragment is for. If a state file is the only thing present, say so and
recommend a live `az` capture instead — state is not a supported input.

## Step 2: Extract each `resource` block

For every `resource "azurerm_<x>" "<local_name>" { … }`:

1. **Translate the type** via `arm-type-canonicalization.md`. A type absent from that
   table is recorded in `warnings[]` as `untranslated_terraform_type` with the local
   name, and the resource is skipped. **Never guess an ARM type from the Terraform
   name** — a wrong type does not fail loudly, it silently fails to match every
   mapping table and the resource falls through the unknown-type policy for the wrong
   reason.
2. **Resolve `name`** from the block's `name` attribute. When it is an expression
   (`"${var.prefix}-app"`, a `format()` call, a `random_*` reference), record the
   expression verbatim in `config.name_expression` and set `name` to the Terraform
   local name prefixed `tf:` (e.g. `tf:api`). Do not attempt to evaluate it. A guessed
   name breaks the drift comparison against a live capture. Add a
   `name_expression_unresolved` warning: the reconstructed `azure_id` then carries a
   `tf:` segment and is **not** a real ARM resource ID, so that resource cannot be
   matched against a live capture — and nothing else in the artifact says so.
3. **Resolve `resource_group_name`.** If it is a reference
   (`azurerm_resource_group.app.name`), follow it to that block's `name`. If that is
   itself an expression, apply rule 2.

   **A CHILD resource inherits its parent's resource group.** Many child types carry no
   `resource_group_name` at all and instead reference the parent
   (`storage_account_id`, `server_id`, `namespace_name`, `virtual_network_name`):
   follow that reference and take the parent's group. Treating an absent
   `resource_group_name` as unresolvable would null out the group for storage shares
   and containers, SQL databases, Event Hubs, Service Bus queues and topics, and Cosmos
   databases — most of a real estate's child resources — and a resource with no group
   cannot be clustered, so the whole cluster seed would collapse.

   Only when neither an explicit group nor a resolvable parent exists: set
   `resource_group: null` and add a `resource_group_unresolved` warning.
4. **Resolve `location`** the same way, into `location`.
5. **Reconstruct `azure_id`** per `arm-type-canonicalization.md` § Reconstructing
   `azure_id`, including the resource-group exception, the implicit-singleton segment
   for storage sub-services, and the `<subscription-unknown>` placeholder rule. When
   the placeholder is used, add ONE `subscription_id_unresolved` warning for the run —
   not one per resource — and set `iac_metadata.subscription_id_source: "unresolved"`.
6. **Set `source: "terraform"`** and record provenance in `config.tf_file`,
   `config.tf_resource_name`, and `config.tf_address`. Provenance is the reason IaC
   stays a first-class source even where live capture is authoritative for state: it
   is what lets Generate emit replacement Terraform that resembles what the customer
   already maintains.

   **`config.tf_address` is `<azurerm_type>.<local_name>`** (e.g.
   `azurerm_subnet.data`), and it is the identity field — `tf_resource_name` alone is
   NOT unique. Terraform namespaces local names per type, so a single module routinely
   contains `azurerm_resource_group.data` and `azurerm_subnet.data`, or
   `azurerm_linux_web_app.storefront` and `azurerm_application_insights.storefront`.
   Anything keyed on the bare local name silently collapses those pairs into one.
7. **Copy the sizing and routing attributes** the mapping tables need — see § Per-type
   attributes.
8. **Extract edges** — see § Edges.

Count `count` and `for_each` as **one** inventory entry, with
`config.multiplicity_expression` set to the expression,
`config.multiplicity_resolved: false`, and a `multiplicity_unresolved` warning. Do not
fan out into N entries: the count is usually a variable, so fanning out invents
resources. Flag it, because a `for_each` over a map of five apps is exactly the case
where the estimate is otherwise five times wrong in the other direction.

## Step 3: Modules are boundaries, not resources

A `module` block is not a resource and gets no inventory entry. If the module source
is a local path, recurse into it and extract its resources, recording the module
address in `config.tf_module`. If the source is a registry or git address whose
content is not in the workspace, add one `module_not_resolved` warning naming the
module and stating that its resources were not discovered — a silently missing module is a
silently missing third of the estate, and this is the single most common reason a
Terraform-only inventory is incomplete.

## Per-type attributes

Only what a downstream table actually reads. Everything else stays out of `config`.

**Omit, do not null.** An attribute the configuration does not set is left OUT of
`config`. Writing `"zone_balancing_enabled": null` for every unset attribute in every
row below turns `config` into mostly noise, and it makes "the customer did not set this"
indistinguishable from "the extractor found nothing to read."

**A type with no row here still gets an entry** — `azure_id`, `azure_type`,
`resource_group`, `subscription_id`, `source`, and the `config.tf_*` provenance are
unconditional. A missing row means "no downstream table reads a sizing or routing
attribute from this type", never "skip the resource".

**If a type below is missing an attribute a mapping table needs, the row is the bug.**
The failure is silent and expensive: the extraction is correct by its own ref, the
inventory passes every shape assertion, and the attribute is simply absent when Design
or Estimate reaches for it. Four rows in this table (Key Vault, Log Analytics, private
endpoints, App Insights) were added after exactly that happened.

| Canonical type                              | Carry into `config`                                                        | Why                                       |
| ------------------------------------------- | -------------------------------------------------------------------------- | ----------------------------------------- |
| `Microsoft.Web/serverfarms`                 | `sku_name`, `worker_count`, `os_type`, `zone_balancing_enabled`             | the plan is the compute unit and its SKU + instance count is what is being paid for |
| `Microsoft.Web/sites`                       | `kind`, `service_plan_id`, `runtime_stack`, `app_setting_names`, `https_only` | `kind` separates web app from function app; the plan link drives the fan-in |
| `Microsoft.Compute/virtualMachines`         | `size`, `os_type`, `image_publisher`, `image_offer`, `image_sku`, `zone`     | size drives right-sizing; the image drives licensing and the Windows x86 path |
| `Microsoft.Compute/virtualMachineScaleSets` | `sku`, `instances`, `os_type`, `image_*`                                     | as above, plus the ASG mapping            |
| `Microsoft.Compute/disks`                   | `storage_account_type`, `disk_size_gb`, `disk_iops_read_write`               | the gp3 → io2 breakpoint                  |
| `Microsoft.ContainerService/managedClusters`| `kubernetes_version`, `default_node_pool` (`vm_size`, `node_count`, `min_count`, `max_count`), `network_plugin` | EKS node sizing |
| `Microsoft.DBforPostgreSQL/flexibleServers` / `...MySQL/...` | `sku_name`, `storage_mb`, `version`, `high_availability`, `zone`, `backup_retention_days` | RDS vs Aurora, and the availability override gate |
| `Microsoft.Sql/servers/databases`           | `sku_name`, `max_size_gb`, `elastic_pool_id`, `zone_redundant`               | an `elastic_pool_id` routes to the specialist gate |
| `Microsoft.DocumentDB/databaseAccounts`     | `kind`, `capabilities`, `consistency_level`, `throughput`, `geo_locations`   | `kind` + `capabilities` select the per-API target (Core/Mongo/Cassandra/Gremlin/Table) |
| `Microsoft.Cache/Redis`                     | `sku_name`, `family`, `capacity`, `shard_count`                             | ElastiCache node sizing                   |
| `Microsoft.Storage/storageAccounts`         | `account_tier`, `account_replication_type`, `account_kind`, `static_website` | S3 mapping; `static_website` is a `static-site-api` pattern signal |
| `Microsoft.Storage/.../fileServices/shares` | `enabled_protocol`, `quota`                                                 | **the EFS-vs-FSx discriminator** — `NFS` → EFS, `SMB` → FSx for Windows File Server |
| `Microsoft.EventHub/namespaces`             | `sku`, `capacity`, `kafka_enabled`, `partition_count`                       | **the MSK-vs-Kinesis discriminator** — `kafka_enabled` → MSK |
| `Microsoft.CognitiveServices/accounts`      | `kind`, `sku_name`                                                          | `kind: OpenAI` is the Azure OpenAI signal, routed to the shared OpenAI→Bedrock guide |
| `Microsoft.Network/virtualNetworks`         | `address_space`, `dns_servers`                                              | VPC CIDR planning                         |
| `Microsoft.Network/virtualNetworks/subnets` | `address_prefixes`, `service_endpoints`, `delegation`                        | subnet layout; a delegation is a hard placement constraint |
| `Microsoft.KeyVault/vaults`                 | `sku_name`, `purge_protection_enabled`, `soft_delete_retention_days`         | `sku_name: premium` means HSM-backed keys, which is a KMS custom-key-store decision rather than plain Secrets Manager — and it is a price difference |
| `Microsoft.OperationalInsights/workspaces`  | `sku`, `retention_in_days`, `daily_quota_gb`                                | the Skip Mapping still needs these: retention and ingest volume are what the CloudWatch Logs fallback costs |
| `Microsoft.Insights/components`             | `application_type`, `workspace_id`                                          | the report names the app type and the workspace link; `workspace_id` is config, NOT an edge (see `schema-discover-azure.md` § Typed edges) |
| `Microsoft.Network/privateEndpoints`        | `subresource_names`                                                         | names WHICH sub-resource is fronted (`postgresqlServer`, `blob`, `vault`), which is what makes the `private_link` edge specific rather than "something connects to something" |
| `Microsoft.Storage/.../blobServices/containers` | `container_access_type`                                                 | `blob` or `container` means public read, which becomes an S3 public-access-block decision |

## Secrets: names only, never values

**This is a hard boundary, and Terraform makes it easy to cross by accident.**

- `app_settings` and `connection_string` blocks: extract **keys only**, into
  `config.app_setting_names` as a sorted array of strings. Never the values.
- `azurerm_key_vault_secret`: inventory the resource, record its `name`, never its
  `value`.
- A literal-looking value anywhere (a connection string, an account key, a password,
  a token) is **discarded**, not recorded and not redacted-in-place — a redacted
  placeholder still tells a reader the field existed and how long it was.
- A `value` that is a Key Vault reference (`@Microsoft.KeyVault(...)`) is retained as
  an **edge** (`secret_ref`), not as a value: the reference is architecture, the
  secret is not.

The phase's postcondition asserts this against the produced artifact, so a slip is a
gate failure rather than a review finding.

## Edges

Terraform expresses relationships as interpolated references, so the edge set comes
from the reference graph rather than from resolved ARM IDs (which the source does not
contain). Resolve each reference to the target's reconstructed `azure_id`.

| Terraform attribute                                                | Edge `type`          | Notes                                                                 |
| ------------------------------------------------------------------ | -------------------- | --------------------------------------------------------------------- |
| `service_plan_id` / `app_service_plan_id` on a site                | `hosted_on`          | **The edge that prevents the 5× App Service Plan cost error.** Always extract it. |
| `subnet_id`, `virtual_network_subnet_id`                           | `network`            | VNet colocation                                                        |
| `private_service_connection.private_connection_resource_id` on a private endpoint | `private_link` | the app-to-data edge; see below                              |
| `@Microsoft.KeyVault(...)` in an app setting, or a `key_vault_id`   | `secret_ref`         | value is never recorded, only the reference                            |
| a reference to a data resource's `fqdn` / `hostname` / `endpoint` / `.id` from a compute resource's config | `data_ref` | **the app-to-data edge.** The commonest real form is an app setting interpolating a database or cache address. It is the edge that merges an app and its database when they sit in different resource groups, so dropping it defeats the merge |
| `principal_id` + `scope` on an `azurerm_role_assignment`           | `identity_grant`     | "app X reads storage Y" — cleaner than GCP exposes it                  |
| `tags` containing `app` or `workload`                              | `declared_affinity`  | declared intent when present; tag KEYS are safe to keep verbatim       |

Set `via` on each edge to the attribute name it came from, so the Clarify assumption
sheet can explain *why* two resources were called one workload.

**Private endpoints are edge-bearing config sources, not mapping targets.** Inventory
the endpoint (a resource absent from the inventory cannot be reported as skipped), but
also emit the `private_link` edge from the endpoint's *consumer* to the resource it
fronts, and add one `warnings[]` entry per consumed endpoint naming the edge it
produced. Structurally this is the same case as gcp's `*_app_version` resources.

**Cross-resource-group edges are the important ones.** An app in `rg-app` referencing
a database in `rg-data` is exactly the horizontal-resource-group layout that
resource-group-seeded clustering gets wrong on its own, so the edge is what later
merges them. Never drop an edge because it crosses a group boundary.

## Validation before returning

- [ ] Every entry's `azure_type` appears in `arm-type-canonicalization.md`.
- [ ] No entry's `azure_type` starts with `azurerm_`.
- [ ] Every `azure_id` is unique, and matches the standard form (or the resource-group exception).
- [ ] Every entry carries `config.tf_address`, and every `tf_address` is unique.
- [ ] Every site with a `service_plan_id` has a `hosted_on` edge.
- [ ] `config.app_setting_names` contains only strings; no `app_settings` values appear anywhere in the contribution.
- [ ] No `tfstate` file was read.
- [ ] Every unresolvable module and every untranslated type has a `warnings[]` entry.
- [ ] Every warning's `code` is from the closed vocabulary in `schema-discover-azure.md` § Warnings.
- [ ] No `config` key holds `null` — an attribute the configuration does not set is omitted.
