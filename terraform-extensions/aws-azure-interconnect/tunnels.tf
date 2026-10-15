# One AWS VPN connection per Azure gateway instance, two tunnels each: four IPsec tunnels, four BGP sessions
locals {
  tunnels = merge([
    for instance in keys(local.vpn_gateway_instances) : {
      for slot in [0, 1] : "${instance}-tunnel${slot + 1}" => {
        azure_instance  = instance
        outside_address = slot == 0 ? aws_vpn_connection.azure[instance].tunnel1_address : aws_vpn_connection.azure[instance].tunnel2_address
        aws_bgp_address = slot == 0 ? aws_vpn_connection.azure[instance].tunnel1_vgw_inside_address : aws_vpn_connection.azure[instance].tunnel2_vgw_inside_address
        preshared_key   = slot == 0 ? aws_vpn_connection.azure[instance].tunnel1_preshared_key : aws_vpn_connection.azure[instance].tunnel2_preshared_key
        azure_bgp_addresses = {
          primary   = local.vpn_gateway_instances.instance0.apipa_bgp_addresses[slot]
          secondary = local.vpn_gateway_instances.instance1.apipa_bgp_addresses[slot]
        }
      }
    }
  ]...)

  ipsec = {
    encryption      = "AES256"
    dh_group        = 14
    sa_lifetime     = 3600
    ike_sa_lifetime = 28800
  }
}

resource "aws_customer_gateway" "azure" {
  for_each = local.vpn_gateway_instances

  region     = local.aws.region
  bgp_asn    = local.vpn_gateway_asn
  ip_address = azurerm_public_ip.vpn_gateway[each.key].ip_address
  type       = "ipsec.1"

  tags = { Name = "${local.name}-azure-${each.key}" }
}

resource "aws_vpn_connection" "azure" {
  for_each = local.vpn_gateway_instances

  region              = local.aws.region
  transit_gateway_id  = aws_ec2_transit_gateway.hub.id
  customer_gateway_id = aws_customer_gateway.azure[each.key].id
  type                = "ipsec.1"

  tunnel1_inside_cidr                  = "${cidrhost("${each.value.apipa_bgp_addresses[0]}/30", 0)}/30"
  tunnel1_ike_versions                 = ["ikev2"]
  tunnel1_phase1_encryption_algorithms = [local.ipsec.encryption]
  tunnel1_phase1_integrity_algorithms  = ["SHA2-256"]
  tunnel1_phase1_dh_group_numbers      = [local.ipsec.dh_group]
  tunnel1_phase1_lifetime_seconds      = local.ipsec.ike_sa_lifetime
  tunnel1_phase2_encryption_algorithms = [local.ipsec.encryption]
  tunnel1_phase2_integrity_algorithms  = ["SHA2-256"]
  tunnel1_phase2_dh_group_numbers      = [local.ipsec.dh_group]
  tunnel1_phase2_lifetime_seconds      = local.ipsec.sa_lifetime
  tunnel1_dpd_timeout_action           = "restart"

  tunnel2_inside_cidr                  = "${cidrhost("${each.value.apipa_bgp_addresses[1]}/30", 0)}/30"
  tunnel2_ike_versions                 = ["ikev2"]
  tunnel2_phase1_encryption_algorithms = [local.ipsec.encryption]
  tunnel2_phase1_integrity_algorithms  = ["SHA2-256"]
  tunnel2_phase1_dh_group_numbers      = [local.ipsec.dh_group]
  tunnel2_phase1_lifetime_seconds      = local.ipsec.ike_sa_lifetime
  tunnel2_phase2_encryption_algorithms = [local.ipsec.encryption]
  tunnel2_phase2_integrity_algorithms  = ["SHA2-256"]
  tunnel2_phase2_dh_group_numbers      = [local.ipsec.dh_group]
  tunnel2_phase2_lifetime_seconds      = local.ipsec.sa_lifetime
  tunnel2_dpd_timeout_action           = "restart"

  tags = { Name = "${local.name}-azure-${each.key}" }
}

resource "azurerm_local_network_gateway" "aws" {
  for_each = local.tunnels

  name                = "${local.name}-aws-${each.key}"
  resource_group_name = azurerm_resource_group.hub.name
  location            = azurerm_resource_group.hub.location
  gateway_address     = each.value.outside_address

  bgp_settings {
    asn                 = local.transit_gateway_asn
    bgp_peering_address = each.value.aws_bgp_address
  }
}

resource "azurerm_virtual_network_gateway_connection" "aws" {
  for_each = local.tunnels

  name                       = "${local.name}-aws-${each.key}"
  resource_group_name        = azurerm_resource_group.hub.name
  location                   = azurerm_resource_group.hub.location
  type                       = "IPsec"
  connection_protocol        = "IKEv2"
  virtual_network_gateway_id = azurerm_virtual_network_gateway.hub.id
  local_network_gateway_id   = azurerm_local_network_gateway.aws[each.key].id
  shared_key                 = each.value.preshared_key
  bgp_enabled                = true

  custom_bgp_addresses {
    primary   = each.value.azure_bgp_addresses.primary
    secondary = each.value.azure_bgp_addresses.secondary
  }

  ipsec_policy {
    ike_encryption   = local.ipsec.encryption
    ike_integrity    = "SHA256"
    dh_group         = "DHGroup${local.ipsec.dh_group}"
    ipsec_encryption = local.ipsec.encryption
    ipsec_integrity  = "SHA256"
    pfs_group        = "PFS2048"
    sa_lifetime      = local.ipsec.sa_lifetime
  }
}
