# Connects an AWS region's shared VPC and EKS clusters to AKS clusters over an active-active, BGP-routed
# IPsec VPN: a transit gateway attached to the shared VPC and each EKS cluster's VPC, an Azure hub VNet
# with an active-active VPN gateway peered to each AKS cluster's VNet, and four tunnels between them.
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0"
    }
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

locals {
  # The AWS side is the one declared region whose shared network has applied, with its declared EKS clusters
  aws = one(flatten([
    for cloud_account_id, account in var.porter.cloud_accounts : [
      for region, stacks in account.regions : { region = region, shared_network = stacks.shared_network, clusters = stacks.clusters }
      if stacks.shared_network != null
    ] if account.cloud == "aws"
  ]))
  eks_clusters = local.aws.clusters

  # The Azure side is every declared AKS cluster, all in one location
  aks_clusters = merge(flatten([
    for cloud_account_id, account in var.porter.cloud_accounts : [
      for location, stacks in account.regions : {
        for cluster_id, cluster in stacks.clusters : cluster_id => merge(cluster, { location = location })
      }
    ] if account.cloud == "azure"
  ])...)
  azure_location = one(distinct([for cluster in values(local.aks_clusters) : cluster.location]))

  name = "aws-${local.aws.region}--azure-${local.azure_location}"

  transit_gateway_asn = 64512
  vpn_gateway_asn     = 65515

  # The shared VPC's rds subnets, one per availability zone, hold the attachment ENIs and route to the AKS clusters
  datastore_subnets = local.aws.shared_network.subnets.rds
}
