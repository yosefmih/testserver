resource "aws_vpc_peering_connection" "this" {
  vpc_id      = var.cluster_vpc_id
  peer_vpc_id = var.shared_vpc_id
  auto_accept = true

  tags = {
    Name                    = var.cluster_name
    "porter.run/managed"    = "true"
    "porter.run/cluster-id" = tostring(var.cluster_id)
  }

  # tags are set at creation; tags customers or CAPA add later are left alone
  lifecycle {
    ignore_changes = [tags]
  }
}

resource "aws_route" "cluster_to_shared" {
  count = length(var.cluster_route_table_ids)

  route_table_id            = var.cluster_route_table_ids[count.index]
  destination_cidr_block    = var.shared_vpc_cidr
  vpc_peering_connection_id = aws_vpc_peering_connection.this.id
}

resource "aws_route" "shared_to_cluster" {
  for_each = var.shared_route_table_ids

  route_table_id            = each.value
  destination_cidr_block    = var.cluster_vpc_cidr
  vpc_peering_connection_id = aws_vpc_peering_connection.this.id
}
