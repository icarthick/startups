# Extraction rules — Bicep (`*.bicep`)

Loaded by `discover-iac.md` only when `.bicep` files are present. One of three
per-dialect refs; the others are `extract-terraform.md` and `extract-arm.md`. Each
covers surface syntax only — the artifact contract is `schema-discover-azure.md` and
the canonical type vocabulary is `arm-type-canonicalization.md`.

**Type handling is simpler than Terraform.** Bicep states the canonical ARM type and
API version inline (`resource sa 'Microsoft.Storage/storageAccounts@2021-06-01' = {…}`).
Strip the `@<apiVersion>` suffix to get `azure_type`; carry the version in
`config.bicep_api_version`. No `azurerm_*` → `Microsoft.*` translation is needed;
`arm-type-canonicalization.md` is consulted only for the casing/emission convention
and the trap list.

## Step 1: Find the files

Glob `**/*.bicep`, excluding `**/node_modules/` and any path under `$MIGRATION_DIR`.
Read each file. A `.bicep` file with no `resource` declarations contributes nothing
and is not an error — params-only, variable-only, and output-only files are common.

## Step 2: Extract each `resource` declaration

For every `resource <symbol> '<ResourceType>@<apiVersion>' [existing] = {…}` (or
the loop form — see below):

1. **Resolve the type.** Split the quoted type string on `@`. The left half is
   `azure_type` verbatim — `Microsoft.Storage/storageAccounts`. The right half is the
   ARM API version; keep it in `config.bicep_api_version`. **Do not include `@` or
   the version in `azure_type`.**

   Consult `arm-type-canonicalization.md` for the casing/emission convention and the
   trap list (§ Traps). Emit this file's spelling for types listed there. For types
   not in the table, the Bicep declaration IS the canonical ARM string — emit it as
   given (fold case on comparison, emit as declared).

   Set `azure_type_provenance`:
   - **`"table"`** — the stripped type matches a row in `arm-type-canonicalization.md`
     (the most common case for well-known services).
   - **`"derived"`** — not in the table; the namespace is in `fast-path-services.json`
     → `namespace_routing`, confirming it is a known ARM namespace.
   - **`"derived_uncorroborated"`** — not in the table; the namespace is NOT in
     `namespace_routing`. Still emit the resource with a
     `type_derived_uncorroborated` warning.

   **Never record a `type_derived_uncorroborated` warning for a type that IS in
   `arm-type-canonicalization.md`** — the table casing check is not derivation.

2. **Resolve `name`.** Read the `name:` property. A literal string → use it directly.
   An expression (`'prefix-${param.suffix}'`, a function call, a reference like
   `param.value`) → record the expression verbatim in `config.bicep_name_expression`
   and set `name` to the Bicep symbol name prefixed `bicep:` — e.g. `bicep:sa` for
   a resource declared as `resource sa '…' = {…}`. For a resource inside a module,
   qualify it by module address: `bicep:module.webMod.sa`. Add a
   `name_expression_unresolved` warning; the reconstructed `azure_id` carries a
   `bicep:` segment and is not a real ARM resource ID, so it cannot be matched against
   a live capture.

3. **Resolve the resource group.** Bicep templates scoped to a resource group
   (`targetScope = 'resourceGroup'`, the default) deploy all resources into the
   deployment target, which is a runtime value. Apply this heuristic in order:

   a. A **`param` with a matching name and a non-expression `default`** — if the
   template declares `param resourceGroupName string = 'rg-prod'` (or a similarly
   named param) and uses it consistently, use that default as `resource_group`.
   b. A **literal string** used as the resource group in a `resourceGroup().name`
   interpolation or explicit assignment.
   c. **Otherwise**: set `resource_group: null` and add a `resource_group_unresolved`
   warning. Do not invent a group name.

   Child resources that have no group carry their parent's group, exactly as in
   `extract-terraform.md` Step 3.

4. **Resolve `location`.** Read the `location:` property. A literal string → use it.
   A `param location string = '...'` with a default → use the default. A function call
   (`resourceGroup().location`) → set `location: null` (no warning — this is normal).

5. **Reconstruct `azure_id`** per `arm-type-canonicalization.md` § Reconstructing
   `azure_id`, using the same `<subscription-unknown>` placeholder rule. Bicep
   templates never carry the subscription ID; always use `<subscription-unknown>` and
   set `iac_metadata.subscription_id_source: "unresolved"`. Emit ONE
   `subscription_id_unresolved` warning per run, not one per resource.

6. **`existing` keyword.** `resource kv '…' existing = {…}` references a resource
   already deployed — not created by this template. Inventory it normally (a resource
   absent from the inventory cannot be reported as a dependency the workload has), and
   set `config.bicep_existing: true`. Do NOT synthesize deployment config from it;
   its `config` carries only `bicep_existing`, `bicep_api_version`, the provenance
   fields, and any attributes explicitly declared on the block.

7. **Set `source: "bicep"`** and record provenance in `config.bicep_file` (relative
   path from the workspace root), `config.bicep_symbol` (the Bicep symbol name), and
   `config.bicep_address` (module-qualified symbol, e.g. `module.webMod.staticSite`
   for a resource inside a module). For root-level resources, `bicep_address` equals
   `bicep_symbol`.

8. **Copy the sizing and routing attributes** the mapping tables need — see
   § Per-type attributes. The same table as `extract-terraform.md` applies; attribute
   names are the same canonical `config` keys (e.g. `sku_name`, `worker_count`,
   `os_type`). Read them from Bicep's `properties:` block or the top-level block
   depending on where that ARM type places them.

9. **Extract edges** — see § Edges.

**Loop resources (`for` expressions).** `resource r '…' = [for i in range(0, n): {…}]`
counts as **one** inventory entry. Set `config.multiplicity_expression` to the loop
expression text, `config.multiplicity_unresolved: true`, and add a
`multiplicity_unresolved` warning naming the symbol. Do not fan out.

## Step 3: Modules are boundaries, not resources

A `module` block is not a resource and gets no inventory entry. Resolve its source
in this order, and stop at the first that works:

1. **Local path** (`'./modules/network.bicep'`, `'../shared/storage.bicep'`) — the
   file is on disk relative to the current `.bicep` file. Recurse into it and extract
   its resources, recording `config.bicep_module` as the module address
   (e.g. `module.webMod`) and `config.bicep_file` as the module file's path.
2. **Not on disk** — a registry source (`br/public:…`, `br:acr.io/…`) or a local
   path whose file is absent. Add one `module_not_resolved` warning naming the module
   symbol and its source string. Its resources were not discovered.

**Do not attempt to resolve registry modules.** The `az bicep restore` cache or a
`.bicep/` lock directory is not read in this static pass — the same policy as
Terraform's `module_not_resolved` for un-init-ed registry modules.

## Per-type attributes

The same table as `extract-terraform.md` § Per-type attributes — consult it for the
canonical `config` keys. Bicep properties map to the same downstream fields:
`properties.sku.name` → `config.sku_name`, `properties.workerCount` → `config.worker_count`,
etc. Apply the same **"always extract `sku`, `tier`, and `capacity`"** exception for
every resource, listed or not.

**Omit, do not null.** An attribute the template does not set is left OUT of `config`.

## Secrets: names only, never values

**Hard boundary.** Bicep `appSettings` arrays contain `{ name: '…', value: '…' }`
objects. Extract **keys only** into `config.app_setting_names` as a sorted array of
strings. Never the values — not even a redaction placeholder.

- A `value` that is a Key Vault reference (`@Microsoft.KeyVault(...)` or a URI from a
  `kv.properties.vaultUri` symbolic reference) is retained as a `secret_ref` **edge**,
  not as a value: the reference is architecture, the secret is not.
- Any literal-looking secret anywhere (a connection string, a password, a token, a key)
  is **discarded** entirely.
- `.bicepparam` parameter values are discarded — even params wired to app settings.

## Edges

Bicep expresses relationships as **symbolic references** (`resource.property` or
`resource.id`). Resolve each to the target's reconstructed `azure_id`.

| Bicep attribute / pattern                                                                                                                                              | Edge `type`         | Notes                                                                             |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------- | --------------------------------------------------------------------------------- |
| `serverFarmId: plan.id` on a site                                                                                                                                      | `hosted_on`         | **The edge that prevents the 5× App Service Plan cost error.** Always extract it. |
| `subnetId: subnet.id`, `virtualNetworkSubnetId`                                                                                                                        | `network`           | VNet colocation                                                                   |
| `privateServiceConnection.privateConnectionResourceId` on a private endpoint                                                                                           | `private_link`      | explicit app-to-data edge                                                         |
| `@Microsoft.KeyVault(...)` in an app setting value, or `keyVaultId: kv.id`, or `kv.properties.vaultUri` in an app setting value                                        | `secret_ref`        | value is never recorded, only the reference                                       |
| A symbolic reference to a data resource's `.properties.primaryEndpoints.blob`, `.fqdn`, `.host`, `.endpoint`, or `.id` from a compute resource's appSettings or config | `data_ref`          | the app-to-data edge — resolves the symbolic target to its `azure_id`             |
| `principalId` + `scope` on a `Microsoft.Authorization/roleAssignments`                                                                                                 | `identity_grant`    | managed-identity grant                                                            |
| `tags` containing `app` or `workload`                                                                                                                                  | `declared_affinity` | declared intent; tag KEYS only                                                    |

Set `via` on each edge to the Bicep property path it came from (e.g.
`"properties.serverFarmId"`, `"appSettings[STORAGE_URL]"`).

## Validation before returning

- [ ] Every entry's `azure_type` has NO `@` character — the API version suffix was stripped.
- [ ] Every entry carries `config.bicep_api_version` with the stripped version string.
- [ ] Every entry has `source: "bicep"`.
- [ ] Every entry carries `config.bicep_file`, `config.bicep_symbol`, and `config.bicep_address`.
- [ ] Every `existing` resource carries `config.bicep_existing: true`.
- [ ] Every loop resource has `config.multiplicity_unresolved: true` and exactly one inventory entry.
- [ ] Every site with a `serverFarmId` symbolic reference has a `hosted_on` edge.
- [ ] `config.app_setting_names` contains only strings; no app-setting values appear anywhere.
- [ ] Every local module resolved or emitted `module_not_resolved`; none silently ignored.
- [ ] No `config` key holds `null` — an attribute the template does not set is omitted.
- [ ] Every `azure_id` is unique.
- [ ] Every warning's `code` is from the closed vocabulary in `schema-discover-azure.md` § Warnings.
- [ ] Every entry whose block sets `sku`, `sku_name`, `tier`, `capacity`, or `size` carries it in `config`.
