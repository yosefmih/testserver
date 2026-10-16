output "resource_group_name" {
  value = azurerm_resource_group.hub.name
}

output "location" {
  value = azurerm_resource_group.hub.location
}

output "vnet_id" {
  value = azurerm_virtual_network.hub.id
}

output "vnet_name" {
  value = azurerm_virtual_network.hub.name
}

output "vpn_gateway_id" {
  value = azurerm_virtual_network_gateway.hub.id
}

output "vpn_gateway_asn" {
  value = var.vpn_gateway_asn
}

output "vpn_gateway_instances" {
  description = "Public IP and APIPA BGP addresses of each VPN gateway instance"
  value = {
    for instance, config in local.vpn_gateway_instances : instance => {
      public_ip           = azurerm_public_ip.vpn_gateway[instance].ip_address
      apipa_bgp_addresses = config.apipa_bgp_addresses
    }
  }
}
