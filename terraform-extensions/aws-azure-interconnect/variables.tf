variable "hub_vnet_cidr" {
  description = "Address space of the Azure hub VNet; must not overlap the shared VPC or the AKS VNets"
  type        = string
  default     = "100.127.0.0/24"
}

variable "datastore_security_groups" {
  description = "Security groups of datastores in the shared VPC that admit the AKS clusters, as { \"<sg id>\" = <port> }"
  type        = map(number)
  default     = {}
}
