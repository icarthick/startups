terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}

provider "azurerm" {
  features {}
}

resource "azurerm_resource_group" "main" {
  name     = "acme-rg"
  location = "East US"
}

resource "azurerm_service_plan" "main" {
  name                = "acme-asp"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  os_type             = "Linux"
  sku_name            = "P1v2"
}

resource "azurerm_linux_web_app" "api" {
  name                = "acme-api"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  service_plan_id     = azurerm_service_plan.main.id

  site_config {}

  app_settings = {
    DATABASE_URL = "postgresql://..."
    REDIS_URL    = "redis://..."
  }
}

resource "azurerm_postgresql_flexible_server" "db" {
  name                   = "acme-postgres"
  resource_group_name    = azurerm_resource_group.main.name
  location               = azurerm_resource_group.main.location
  version                = "15"
  sku_name               = "GP_Standard_D2s_v3"
  storage_mb             = 32768

  administrator_login    = "acmeadmin"
  administrator_password = "PLACEHOLDER_REDACTED"
}

resource "azurerm_storage_account" "assets" {
  name                     = "acmeassets"
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_key_vault" "secrets" {
  name                = "acme-kv"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku_name            = "standard"
  tenant_id           = "00000000-0000-0000-0000-000000000000"
}
