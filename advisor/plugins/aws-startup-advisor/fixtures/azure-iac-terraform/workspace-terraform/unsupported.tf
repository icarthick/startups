# A COST-BEARING resource type deliberately absent from
# arm-type-canonicalization.md. It carries a sku, so the unknown-type policy must
# STOP on it at Design rather than warn-and-skip. At Discover it must be recorded
# as untranslated in warnings[], NOT guessed into a Microsoft.* string.
resource "azurerm_dev_test_lab" "sandbox" {
  name                = "dtl-${var.prefix}-sandbox"
  resource_group_name = azurerm_resource_group.shared.name
  location            = azurerm_resource_group.shared.location
}

# A module whose source is not in the workspace: its resources cannot be
# discovered, and that must produce a warning rather than silence.
module "cdn" {
  source              = "Azure/cdn/azurerm"
  version             = "3.1.0"
  resource_group_name = azurerm_resource_group.app.name
}
