output "transit_gateway_id" {
  value = aws_ec2_transit_gateway.hub.id
}

output "vpn_gateway_id" {
  value = azurerm_virtual_network_gateway.hub.id
}

output "tunnels" {
  description = "The four IPsec tunnels and their BGP peerings"
  value = {
    for key, tunnel in local.tunnels : key => {
      azure_public_ip     = azurerm_public_ip.vpn_gateway[tunnel.azure_instance].ip_address
      aws_outside_ip      = tunnel.outside_address
      aws_bgp_address     = tunnel.aws_bgp_address
      azure_bgp_addresses = tunnel.azure_bgp_addresses
    }
  }
}

output "reachable" {
  description = "What each side can reach once BGP is up"
  value = {
    from_aws   = [for cluster in values(local.aks_clusters) : cluster.vnet.cidr]
    from_azure = local.aws.shared_network.vpc.cidr
  }
}
