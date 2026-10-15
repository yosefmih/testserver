# Porter used to run this folder as module "extension" and key the datastore routes by subnet name. These
# blocks carry the resources it created then into this layout; delete the file once a run has applied it.
moved {
  from = module.extension.aws_ec2_transit_gateway.hub
  to   = aws_ec2_transit_gateway.hub
}

moved {
  from = module.extension.aws_ec2_transit_gateway_vpc_attachment.shared
  to   = aws_ec2_transit_gateway_vpc_attachment.shared
}

moved {
  from = module.extension.aws_customer_gateway.azure
  to   = aws_customer_gateway.azure
}

moved {
  from = module.extension.aws_vpn_connection.azure
  to   = aws_vpn_connection.azure
}

moved {
  from = module.extension.aws_route.datastore_to_aks_cluster["porter-shared-rds-private-us-west-2a:25"]
  to   = aws_route.datastore_to_aks_cluster["us-west-2a:25"]
}

moved {
  from = module.extension.aws_route.datastore_to_aks_cluster["porter-shared-rds-private-us-west-2b:25"]
  to   = aws_route.datastore_to_aks_cluster["us-west-2b:25"]
}

moved {
  from = module.extension.aws_route.datastore_to_aks_cluster["porter-shared-rds-private-us-west-2c:25"]
  to   = aws_route.datastore_to_aks_cluster["us-west-2c:25"]
}

moved {
  from = module.extension.azurerm_resource_group.hub
  to   = azurerm_resource_group.hub
}

moved {
  from = module.extension.azurerm_virtual_network.hub
  to   = azurerm_virtual_network.hub
}

moved {
  from = module.extension.azurerm_subnet.gateway
  to   = azurerm_subnet.gateway
}

moved {
  from = module.extension.azurerm_public_ip.vpn_gateway
  to   = azurerm_public_ip.vpn_gateway
}

moved {
  from = module.extension.azurerm_virtual_network_gateway.hub
  to   = azurerm_virtual_network_gateway.hub
}

moved {
  from = module.extension.azurerm_local_network_gateway.aws
  to   = azurerm_local_network_gateway.aws
}

moved {
  from = module.extension.azurerm_virtual_network_gateway_connection.aws
  to   = azurerm_virtual_network_gateway_connection.aws
}

moved {
  from = module.extension.azurerm_virtual_network_peering.hub_to_aks_cluster
  to   = azurerm_virtual_network_peering.hub_to_aks_cluster
}

moved {
  from = module.extension.azurerm_virtual_network_peering.aks_cluster_to_hub
  to   = azurerm_virtual_network_peering.aks_cluster_to_hub
}
