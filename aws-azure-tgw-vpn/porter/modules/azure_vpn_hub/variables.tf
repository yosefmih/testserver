variable "name" {
  description = "Prefix of the hub's resource group, VNet and VPN gateway"
  type        = string
}

variable "location" {
  description = "Azure region of the hub"
  type        = string
}

variable "vnet_cidr" {
  description = "Address space of the hub VNet; the GatewaySubnet is its first /27"
  type        = string

  validation {
    condition     = tonumber(split("/", var.vnet_cidr)[1]) <= 27
    error_message = "vnet_cidr must be a /27 or larger to fit the GatewaySubnet."
  }
}

variable "vpn_gateway_sku" {
  description = "Zone redundant VPN gateway SKU"
  type        = string
  default     = "VpnGw2AZ"
}

variable "vpn_gateway_asn" {
  description = "BGP ASN of the VPN gateway"
  type        = number
  default     = 65515
}
