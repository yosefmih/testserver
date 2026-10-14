# Connects an AWS region's shared VPC to AKS clusters over an active-active, BGP-routed IPsec VPN:
# a transit gateway attached to the shared VPC, an Azure hub VNet with an active-active VPN gateway
# peered to each cluster's VNet, and four tunnels between them.
locals {
  aws_region     = try(var.inputs.aws_region, keys(var.porter.stacks.regional_backbones)[0])
  shared_network = var.porter.stacks.regional_backbones[local.aws_region]
  aks_clusters   = { for id in var.inputs.aks_cluster_ids : tostring(id) => var.porter.stacks.clusters[tostring(id)] }
  azure_location = one(distinct([for cluster in values(local.aks_clusters) : cluster.location]))

  name                      = "aws-${local.aws_region}--azure-${local.azure_location}"
  hub_vnet_cidr             = try(var.inputs.hub_vnet_cidr, "100.127.0.0/24")
  datastore_security_groups = try(var.inputs.datastore_security_groups, {})

  transit_gateway_asn = 64512
  vpn_gateway_asn     = 65515

  # The shared VPC's datastore subnets hold the attachment ENIs and route to the AKS clusters
  datastore_subnets = [for subnet in local.shared_network.subnets : subnet if subnet.service == "rds"]
}

provider "aws" {
  region = local.aws_region
}
