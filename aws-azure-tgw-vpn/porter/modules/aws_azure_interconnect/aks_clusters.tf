data "azurerm_virtual_network" "aks_cluster" {
  for_each = var.aks_clusters

  resource_group_name = each.value.resource_group_name
  name                = each.value.vnet_name
}

resource "azurerm_virtual_network_peering" "hub_to_aks_cluster" {
  for_each = var.aks_clusters

  name                      = "${var.name}-hub-to-${each.key}"
  resource_group_name       = var.azure_vpn_hub.resource_group_name
  virtual_network_name      = var.azure_vpn_hub.vnet_name
  remote_virtual_network_id = data.azurerm_virtual_network.aks_cluster[each.key].id
  allow_forwarded_traffic   = true
  allow_gateway_transit     = true
}

resource "azurerm_virtual_network_peering" "aks_cluster_to_hub" {
  for_each = var.aks_clusters

  name                      = "${var.name}-${each.key}-to-hub"
  resource_group_name       = each.value.resource_group_name
  virtual_network_name      = each.value.vnet_name
  remote_virtual_network_id = var.azure_vpn_hub.vnet_id
  allow_forwarded_traffic   = true
  use_remote_gateways       = true

  depends_on = [azurerm_virtual_network_peering.hub_to_aks_cluster]
}
