# Each gateway instance holds one APIPA BGP address per AWS tunnel slot; the AWS tunnel CIDRs are the
# /30s holding them
locals {
  vpn_gateway_instances = {
    instance0 = { apipa_bgp_addresses = ["169.254.21.2", "169.254.22.2"] }
    instance1 = { apipa_bgp_addresses = ["169.254.21.6", "169.254.22.6"] }
  }
}

resource "azurerm_resource_group" "hub" {
  name     = "${local.name}-hub"
  location = local.azure_location
}

resource "azurerm_virtual_network" "hub" {
  name                = "${local.name}-hub"
  resource_group_name = azurerm_resource_group.hub.name
  location            = azurerm_resource_group.hub.location
  address_space       = [local.hub_vnet_cidr]
}

resource "azurerm_subnet" "gateway" {
  name                 = "GatewaySubnet"
  resource_group_name  = azurerm_resource_group.hub.name
  virtual_network_name = azurerm_virtual_network.hub.name
  address_prefixes     = [cidrsubnet(local.hub_vnet_cidr, 27 - tonumber(split("/", local.hub_vnet_cidr)[1]), 0)]
}

resource "azurerm_public_ip" "vpn_gateway" {
  for_each = local.vpn_gateway_instances

  name                = "${local.name}-vpngw-${each.key}"
  resource_group_name = azurerm_resource_group.hub.name
  location            = azurerm_resource_group.hub.location
  allocation_method   = "Static"
  sku                 = "Standard"
  zones               = ["1", "2", "3"]
}

resource "azurerm_virtual_network_gateway" "hub" {
  name                = "${local.name}-vpngw"
  resource_group_name = azurerm_resource_group.hub.name
  location            = azurerm_resource_group.hub.location
  type                = "Vpn"
  vpn_type            = "RouteBased"
  sku                 = "VpnGw2AZ"
  generation          = "Generation2"
  active_active       = true
  bgp_enabled         = true

  dynamic "ip_configuration" {
    for_each = local.vpn_gateway_instances

    content {
      name                          = ip_configuration.key
      public_ip_address_id          = azurerm_public_ip.vpn_gateway[ip_configuration.key].id
      private_ip_address_allocation = "Dynamic"
      subnet_id                     = azurerm_subnet.gateway.id
    }
  }

  bgp_settings {
    asn = local.vpn_gateway_asn

    dynamic "peering_addresses" {
      for_each = local.vpn_gateway_instances

      content {
        ip_configuration_name = peering_addresses.key
        apipa_addresses       = peering_addresses.value.apipa_bgp_addresses
      }
    }
  }
}
