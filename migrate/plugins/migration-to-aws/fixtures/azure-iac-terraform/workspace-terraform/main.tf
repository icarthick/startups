# Synthetic Azure estate. Every block here exists to pin one decision the skill
# must make from a table rather than from a plausible guess. See ../README.md.

terraform {
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 4.0" }
  }
}

provider "azurerm" {
  features {}
  # Deliberately no subscription_id: it comes from ARM_SUBSCRIPTION_ID in the
  # environment. Pins the <subscription-unknown> placeholder rule.
}

variable "prefix" {
  type    = string
  default = "contoso"
}

# --- Horizontal resource-group layout: app and data deliberately separated. ---
# Pins the cross-RG edge that later merges them into one cluster.
resource "azurerm_resource_group" "app" {
  name     = "rg-app"
  location = "westeurope"
}

resource "azurerm_resource_group" "data" {
  name     = "rg-data"
  location = "westeurope"
}

# rg-shared holds two UNRELATED workloads with no edges between them.
# Pins the split.
resource "azurerm_resource_group" "shared" {
  name     = "rg-shared"
  location = "westeurope"
}
