# Each AKS cluster's VNet reaches AWS through the hub's gateway, which advertises the VNet over BGP
resource "azurerm_virtual_network_peering" "hub_to_aks_cluster" {
  for_each = local.aks_clusters

  name                      = "${local.name}-hub-to-${each.value.cluster_name}"
  resource_group_name       = azurerm_resource_group.hub.name
  virtual_network_name      = azurerm_virtual_network.hub.name
  remote_virtual_network_id = each.value.vnet_id
  allow_forwarded_traffic   = true
  allow_gateway_transit     = true

  depends_on = [azurerm_virtual_network_gateway.hub]
}

resource "azurerm_virtual_network_peering" "aks_cluster_to_hub" {
  for_each = local.aks_clusters

  name                      = "${local.name}-${each.value.cluster_name}-to-hub"
  resource_group_name       = each.value.resource_group_name
  virtual_network_name      = each.value.vnet_name
  remote_virtual_network_id = azurerm_virtual_network.hub.id
  allow_forwarded_traffic   = true
  use_remote_gateways       = true

  depends_on = [azurerm_virtual_network_peering.hub_to_aks_cluster]
}
