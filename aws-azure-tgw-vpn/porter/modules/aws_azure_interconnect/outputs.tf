output "aws_vpn_connection_ids" {
  value = { for instance, connection in aws_vpn_connection.azure : instance => connection.id }
}

output "tunnels" {
  description = "The four IPsec tunnels and their BGP peerings"
  value = {
    for key, tunnel in local.tunnels : key => {
      azure_public_ip     = local.azure_instances[tunnel.azure_instance].public_ip
      aws_outside_ip      = tunnel.outside_address
      aws_bgp_address     = tunnel.aws_bgp_address
      azure_bgp_addresses = tunnel.azure_bgp_addresses
    }
  }
}

output "aks_cluster_cidrs" {
  value = local.aks_cluster_cidrs
}
