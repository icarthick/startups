# Schema — Azure discovery artifacts

Contract for the two artifacts the discover phase produces. `discover-assemble.md` is
their single creator and owns the validation checklist at the bottom.

## `azure-resource-inventory.json`

```jsonc
{
  "phase": "discover",
  "metadata": {
    "discovery_timestamp": "<ISO 8601>",
    "discovery_sources": ["terraform"],   // only sources that CONTRIBUTED, never merely ran
    "subscriptions_discovered": ["<subscription id>"],
    "total_resources": 0,
    "confidence": "inferred"              // deterministic | measured | inferred | billing_inferred
  },
  "resources": [
    {
      "azure_id": "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Web/serverfarms/<name>",
      "azure_type": "Microsoft.Web/serverfarms",   // canonical ARM type; never azurerm_*
      "name": "<name>",
      "resource_group": "<rg>",
      "subscription_id": "<sub>",
      "location": "<azure region>",
      "source": "terraform",              // terraform | bicep | arm | live | rdfa | billing (or a "+"-joined set)
      "config": {},                       // per-type; NAMES only for app settings, connection strings, Key Vault entries
      "tags": {},
      "edges": [],                        // see § Typed edges
      "drift": []                         // see § Drift records
    }
  ],
  "iac_metadata": {},                     // present only when a dialect actually contributed
  "unclustered": []                       // azure_ids no cluster claimed
}
```

`azure_id` is the artifact's primary key and its stable address. It is preferred over
a Terraform address because it embeds the subscription and the resource group, so one
field supplies the cluster seed key, the environment scope, and uniqueness with no
derivation. Only Terraform-sourced resources need it reconstructed; Bicep, ARM, live
`az`, and RDfA all supply it.

### Typed edges

Each edge is `{ "type": "<edge type>", "to": "<azure_id>", "via": "<property>" }`.
Azure embeds full ARM resource IDs inside resource *properties*, so edges survive
every discovery source — unlike GCP, where the graph comes from Terraform reference
expressions and therefore exists only when IaC does.

| Edge type          | Signal                                              | Why it matters                                   |
| ------------------ | --------------------------------------------------- | ------------------------------------------------ |
| `hosted_on`        | `serverFarmId` on a web app → App Service Plan      | hard edge; also what fixes the plan cost trap    |
| `network`          | `subnetId` / `virtualNetworkSubnetId`               | VNet colocation                                  |
| `private_link`     | private endpoint → the resource it fronts           | explicit app-to-data edge                        |
| `secret_ref`       | Key Vault reference in app settings                 | secret dependency                                |
| `identity_grant`   | managed identity + role-assignment scope            | "app X reads storage Y"                          |
| `declared_affinity`| `app=` / `workload=` tags                           | declared intent, when present                    |

### Drift records

`{ "field": "<path>", "values": [{ "source": "terraform", "value": ... }, { "source": "live", "value": ... }], "won": "live" }`

A disagreement between sources is **never** silently reconciled. Both values are kept
with their sources and the winner recorded, so the report can say "your Terraform
declares `Standard_D2s_v3`, your tenant is running `Standard_D4s_v3`". Drift the
customer did not know they had is a deliverable, not a nuisance.

## `azure-resource-clusters.json`

```jsonc
{
  "phase": "discover",
  "clusters": [
    {
      "cluster_id": "<stable slug>",
      "seed_resource_group": "<rg>",     // the seed, not the answer
      "tier": "compute",                  // network_identity_secrets | data | compute | edge
      "members": ["<azure_id>"],
      "primary": "<azure_id>",            // the resource the cluster is named for
      "edges": [],                        // the edge set that JUSTIFIED this grouping
      "pattern_id": "unclassified",
      "pattern_confidence": "inferred"
    }
  ],
  "unclustered": []
}
```

`edges` is not decoration. The Clarify assumption sheet needs it to explain *why* five
resources were called one workload, and a cluster the user cannot see the reasoning
for is a cluster they cannot validate.

`tier` is a fixed classification, not a computed topological depth. Fixed tiers are
what Generate's cutover sequencing actually wants, and they are stable under partial
discovery in a way a depth calculation is not.

## Validation Checklist

- [ ] Every `resources[]` entry has `azure_id`, `azure_type`, `resource_group`, `subscription_id`, `source`, `config`.
- [ ] No `azure_type` value matches `azurerm_*` — translation happened during extraction.
- [ ] `azure_id` is unique across `resources[]`.
- [ ] `metadata.discovery_sources` lists only sources that contributed at least one resource.
- [ ] For each dialect whose files were found in the workspace, at least one resource carries that dialect as its `source`.
- [ ] No app-setting value, connection-string value, storage key, or Key Vault secret value appears anywhere.
- [ ] Every inventory resource is either a cluster member or listed in `unclustered[]`.
- [ ] Every cluster has `cluster_id`, `tier`, `members`, and the `edges[]` that justified it.

## Status — skeleton (build step 1)

The shapes above are the real contract and downstream phases are written against them.
Per-type `config` schemas land with each dialect and source (step 2); the reservation
and utilization profiles land with the RDfA fragment (step 2); `pattern_id`'s value set
lands with the pattern catalog (step 4).
