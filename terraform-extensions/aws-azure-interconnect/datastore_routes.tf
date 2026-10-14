# The shared VPC learns nothing over BGP, so its datastore route tables point each AKS VNet at the
# transit gateway, and each datastore security group admits the AKS VNets on its port
locals {
  datastore_routes = {
    for pair in setproduct(local.datastore_subnets, values(local.aks_clusters)) :
    "${pair[0].name}:${pair[1].cluster_id}" => {
      route_table_id = local.shared_network.route_table_ids[pair[0].name]
      cidr           = pair[1].vnet_cidr
    }
  }

  datastore_ingress_rules = {
    for pair in setproduct(keys(local.datastore_security_groups), values(local.aks_clusters)) :
    "${pair[0]}:${pair[1].cluster_id}" => {
      security_group_id = pair[0]
      port              = local.datastore_security_groups[pair[0]]
      cidr              = pair[1].vnet_cidr
      cluster_name      = pair[1].cluster_name
    }
  }
}

resource "aws_route" "datastore_to_aks_cluster" {
  for_each = local.datastore_routes

  route_table_id         = each.value.route_table_id
  destination_cidr_block = each.value.cidr
  transit_gateway_id     = aws_ec2_transit_gateway.hub.id

  depends_on = [aws_ec2_transit_gateway_vpc_attachment.shared]
}

resource "aws_vpc_security_group_ingress_rule" "aks_cluster_to_datastore" {
  for_each = local.datastore_ingress_rules

  security_group_id = each.value.security_group_id
  cidr_ipv4         = each.value.cidr
  ip_protocol       = "tcp"
  from_port         = each.value.port
  to_port           = each.value.port
  description       = "${local.name} ${each.value.cluster_name}"
}
