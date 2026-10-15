# The shared VPC learns nothing over BGP, so its datastore route tables point each AKS VNet at the
# transit gateway, and each datastore security group admits the AKS VNets on its port
locals {
  datastore_routes = {
    for pair in setproduct(keys(local.datastore_subnets), keys(local.aks_clusters)) :
    "${pair[0]}:${pair[1]}" => {
      route_table_id = local.datastore_subnets[pair[0]].route_table_id
      cidr           = local.aks_clusters[pair[1]].vnet.cidr
    }
  }

  datastore_ingress_rules = {
    for pair in setproduct(keys(var.datastore_security_groups), keys(local.aks_clusters)) :
    "${pair[0]}:${pair[1]}" => {
      security_group_id = pair[0]
      port              = var.datastore_security_groups[pair[0]]
      cidr              = local.aks_clusters[pair[1]].vnet.cidr
      cluster_name      = local.aks_clusters[pair[1]].name
    }
  }
}

resource "aws_route" "datastore_to_aks_cluster" {
  for_each = local.datastore_routes

  region                 = local.aws.region
  route_table_id         = each.value.route_table_id
  destination_cidr_block = each.value.cidr
  transit_gateway_id     = aws_ec2_transit_gateway.hub.id

  depends_on = [aws_ec2_transit_gateway_vpc_attachment.shared]
}

resource "aws_vpc_security_group_ingress_rule" "aks_cluster_to_datastore" {
  for_each = local.datastore_ingress_rules

  region            = local.aws.region
  security_group_id = each.value.security_group_id
  cidr_ipv4         = each.value.cidr
  ip_protocol       = "tcp"
  from_port         = each.value.port
  to_port           = each.value.port
  description       = "${local.name} ${each.value.cluster_name}"
}
