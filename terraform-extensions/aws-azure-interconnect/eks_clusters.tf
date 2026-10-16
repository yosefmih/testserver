# Each EKS cluster's VPC attaches to the transit gateway, which advertises the VPC to the AKS VNets over BGP.
# The VPC learns nothing over BGP, so its private route tables point each AKS VNet at the transit gateway,
# and the EKS cluster security group, which every node carries, admits the AKS VNets.
locals {
  eks_cluster_routes = merge([
    for eks_cluster_id, cluster in local.eks_clusters : {
      for pair in setproduct(keys(cluster.subnets.private), keys(local.aks_clusters)) :
      "${eks_cluster_id}:${pair[0]}:${pair[1]}" => {
        route_table_id = cluster.subnets.private[pair[0]].route_table_id
        cidr           = local.aks_clusters[pair[1]].vnet.cidr
      }
    }
  ]...)

  eks_cluster_ingress_rules = {
    for pair in setproduct(keys(local.eks_clusters), keys(local.aks_clusters)) :
    "${pair[0]}:${pair[1]}" => {
      eks_cluster_id   = pair[0]
      cidr             = local.aks_clusters[pair[1]].vnet.cidr
      aks_cluster_name = local.aks_clusters[pair[1]].name
    }
  }
}

resource "aws_ec2_transit_gateway_vpc_attachment" "eks_cluster" {
  for_each = local.eks_clusters

  region             = local.aws.region
  transit_gateway_id = aws_ec2_transit_gateway.hub.id
  vpc_id             = each.value.vpc.id
  subnet_ids         = [for subnet in values(each.value.subnets.private) : subnet.id]

  tags = { Name = "${local.name}-${each.value.name}" }
}

resource "aws_route" "eks_cluster_to_aks_cluster" {
  for_each = local.eks_cluster_routes

  region                 = local.aws.region
  route_table_id         = each.value.route_table_id
  destination_cidr_block = each.value.cidr
  transit_gateway_id     = aws_ec2_transit_gateway.hub.id

  depends_on = [aws_ec2_transit_gateway_vpc_attachment.eks_cluster]
}

data "aws_eks_cluster" "eks_cluster" {
  for_each = local.eks_clusters

  region = local.aws.region
  name   = each.value.name
}

resource "aws_vpc_security_group_ingress_rule" "aks_cluster_to_eks_cluster" {
  for_each = local.eks_cluster_ingress_rules

  region            = local.aws.region
  security_group_id = data.aws_eks_cluster.eks_cluster[each.value.eks_cluster_id].vpc_config[0].cluster_security_group_id
  cidr_ipv4         = each.value.cidr
  ip_protocol       = "-1"
  description       = "${local.name} ${each.value.aks_cluster_name}"
}
