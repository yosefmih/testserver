variable "name" {
  description = "Prefix of every resource the interconnect creates, on both clouds"
  type        = string
}

variable "aws_transit_gateway" {
  description = "Outputs of the aws_transit_gateway module"
  type = object({
    id  = string
    asn = number
  })
}

variable "azure_vpn_hub" {
  description = "Outputs of the azure_vpn_hub module"
  type = object({
    resource_group_name = string
    location            = string
    vnet_id             = string
    vnet_name           = string
    vpn_gateway_id      = string
    vpn_gateway_asn     = number
    vpn_gateway_instances = map(object({
      public_ip           = string
      apipa_bgp_addresses = list(string)
    }))
  })
}

variable "aks_clusters" {
  description = "AKS clusters whose VNets are peered to the hub, by Porter cluster name"
  type = map(object({
    resource_group_name = string
    vnet_name           = string
  }))
  default = {}
}

variable "datastore_route_table_ids" {
  description = "Shared VPC route tables of the datastore subnets; they get routes to every AKS cluster"
  type        = list(string)
  default     = []
}

variable "datastore_routes" {
  description = "Datastores reachable from an AKS cluster, by \"<datastore>--<cluster>\". The datastore security group is the boundary between pairs."
  type = map(object({
    aks_cluster                 = string
    datastore_security_group_id = string
    datastore_port              = number
  }))
  default = {}
}
