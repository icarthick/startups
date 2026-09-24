// azure-iac-bicep fixture — covers Bicep-specific divergences from Terraform extraction.
// See README.md for the design rationale.
//
// Resources covered:
//   1. storageAccount  — api-version stripping: @2021-06-01 must be absent from azure_type
//   2. appServicePlan  — symbolic-ref source for a hosted_on edge
//   3. webApp          — hosted_on edge (plan.id), data_ref edge (storage endpoint),
//                        secret_ref edge (KV URI), secret boundary (sentinel must be discarded)
//   4. existingKeyVault  — 'existing' keyword: config.bicep_existing must be true
//   5. logWorkspace    — for-loop: single entry with config.multiplicity_unresolved: true
//   6. module webMod   — local module: its resource discovered with bicep_module provenance
//   7. module sharedNet — NOT on disk: must produce a module_not_resolved warning

targetScope = 'resourceGroup'

param location string = 'westeurope'
param resourceGroupName string = 'rg-bicep-app'

// --- api-version stripping ---
// azure_type must be 'Microsoft.Storage/storageAccounts', NOT 'Microsoft.Storage/storageAccounts@2021-06-01'.
// config.bicep_api_version must be '2021-06-01'.
resource storageAccount 'Microsoft.Storage/storageAccounts@2021-06-01' = {
  name: 'sa-bicep-fixture'
  location: location
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    accessTier: 'Hot'
  }
}

// --- symbolic-ref edge source ---
// webApp.properties.serverFarmId: appServicePlan.id produces a hosted_on edge.
resource appServicePlan 'Microsoft.Web/serverfarms@2022-09-01' = {
  name: 'asp-bicep-fix'
  location: location
  sku: {
    name: 'P1v3'
    capacity: 2
  }
  kind: 'linux'
  properties: {
    reserved: true
  }
}

// --- symbolic-ref edges + secret boundary ---
// hosted_on: serverFarmId resolves to appServicePlan.id
// data_ref:  STORAGE_URL value is storageAccount.properties.primaryEndpoints.blob
// secret_ref: KV_URI value is existingKeyVault.properties.vaultUri
// FIXTURE_SENTINEL_MUST_NOT_APPEAR is the secret-boundary sentinel — its VALUE must be
// discarded entirely; 'API_SECRET' must appear only in app_setting_names, never with its value.
resource webApp 'Microsoft.Web/sites@2022-09-01' = {
  name: 'app-bicep-fix'
  location: location
  kind: 'app,linux'
  properties: {
    serverFarmId: appServicePlan.id
    httpsOnly: true
    siteConfig: {
      appSettings: [
        {
          name: 'STORAGE_URL'
          value: storageAccount.properties.primaryEndpoints.blob
        }
        {
          name: 'KV_URI'
          value: existingKeyVault.properties.vaultUri
        }
        {
          name: 'API_SECRET'
          value: 'FIXTURE_SENTINEL_MUST_NOT_APPEAR'
        }
      ]
    }
  }
}

// --- existing keyword ---
// Must appear in inventory with config.bicep_existing: true.
// Not created by this template; the workload depends on it and Design needs it.
resource existingKeyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: 'kv-existing-fix'
}

// --- loop resource (for expression) ---
// A for expression produces ONE inventory entry with config.multiplicity_unresolved: true.
// Name 'log-ws-${i}' is an expression; name in inventory is 'bicep:logWorkspace'.
resource logWorkspace 'Microsoft.OperationalInsights/workspaces@2022-10-01' = [for i in range(0, 3): {
  name: 'log-ws-${i}'
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}]

// --- local module ---
// ./modules/web.bicep is on disk; its resource must be discovered and carry
// config.bicep_module: 'module.webMod'.
module webMod './modules/web.bicep' = {
  name: 'webModule'
  params: {
    location: location
    resourceGroupName: resourceGroupName
  }
}

// --- registry module NOT on disk ---
// 'br/public:network/virtual-network:6.0.0' is not present in the workspace.
// Must produce a module_not_resolved warning naming 'sharedNetworkModule'.
module sharedNet 'br/public:network/virtual-network:6.0.0' = {
  name: 'sharedNetworkModule'
  params: {
    addressPrefixes: ['10.1.0.0/16']
    location: location
  }
}
