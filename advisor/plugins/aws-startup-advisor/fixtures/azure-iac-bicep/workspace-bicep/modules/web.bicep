// Local module for the azure-iac-bicep fixture.
// Provides one resource to verify that extract-bicep.md recurses into local modules
// and tags each resource with config.bicep_module: 'module.webMod'.

param location string
param resourceGroupName string

resource staticSite 'Microsoft.Web/staticSites@2022-09-01' = {
  name: 'static-bicep-fix'
  location: location
  sku: {
    name: 'Free'
    tier: 'Free'
  }
}
