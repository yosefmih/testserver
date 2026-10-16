locals {
  aks_cluster_cidrs = {
    for name, vnet in data.azurerm_virtual_network.aks_cluster : name => vnet.address_space
  }

  datastore_routes_to_aks_clusters = {
    for pair in setproduct(var.datastore_route_table_ids, flatten(values(local.aks_cluster_cidrs))) :
    "${pair[0]}:${pair[1]}" => { route_table_id = pair[0], cidr = pair[1] }
  }

  datastore_ingress_rules = merge([
    for key, route in var.datastore_routes : {
      for cidr in local.aks_cluster_cidrs[route.aks_cluster] : "${key}:${cidr}" => merge(route, { cidr = cidr })
    }
  ]...)
}

resource "aws_route" "datastore_to_aks_cluster" {
  for_each = local.datastore_routes_to_aks_clusters

  route_table_id         = each.value.route_table_id
  destination_cidr_block = each.value.cidr
  transit_gateway_id     = var.aws_transit_gateway.id
}

resource "aws_vpc_security_group_ingress_rule" "aks_cluster_to_datastore" {
  for_each = local.datastore_ingress_rules

  security_group_id = each.value.datastore_security_group_id
  cidr_ipv4         = each.value.cidr
  ip_protocol       = "tcp"
  from_port         = each.value.datastore_port
  to_port           = each.value.datastore_port
  description       = "${var.name} ${each.key}"
}
