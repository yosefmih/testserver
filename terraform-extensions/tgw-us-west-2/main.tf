locals {
  shared_network  = var.porter.stacks[var.inputs.region_stack].shared_network
  cluster_network = var.porter.stacks[var.inputs.cluster_stack].network
  remote_cidrs    = try(var.inputs.remote_cidrs, [])

  # A transit gateway attachment takes one subnet per availability zone
  shared_attachment_subnet_ids  = [for subnet in local.shared_network.subnets : subnet.id if subnet.service == "customer"]
  cluster_attachment_subnet_ids = [for subnet in local.cluster_network.private_subnets : subnet.id]

  shared_route_table_ids  = values(local.shared_network.route_table_ids)
  cluster_route_table_ids = concat(local.cluster_network.public_route_table_ids, local.cluster_network.private_route_table_ids)
}

resource "aws_ec2_transit_gateway" "this" {
  description                     = "Connects Porter's shared VPC and cluster VPC in this region"
  default_route_table_association = "enable"
  default_route_table_propagation = "enable"
  dns_support                     = "enable"

  tags = {
    Name = "porter-extension-tgw"
  }
}

resource "aws_ec2_transit_gateway_vpc_attachment" "shared" {
  transit_gateway_id = aws_ec2_transit_gateway.this.id
  vpc_id             = local.shared_network.vpc_id
  subnet_ids         = local.shared_attachment_subnet_ids

  tags = {
    Name = "porter-extension-tgw-shared"
  }
}

resource "aws_ec2_transit_gateway_vpc_attachment" "cluster" {
  transit_gateway_id = aws_ec2_transit_gateway.this.id
  vpc_id             = local.cluster_network.vpc_id
  subnet_ids         = local.cluster_attachment_subnet_ids

  tags = {
    Name = "porter-extension-tgw-cluster"
  }
}

# Routes to the remote networks, added to Porter's route tables as separate entries. Porter's own
# routes between the two VPCs (the peering) are left alone.
resource "aws_route" "shared_to_remote" {
  for_each = {
    for pair in setproduct(local.shared_route_table_ids, local.remote_cidrs) : "${pair[0]}|${pair[1]}" => pair
  }

  route_table_id         = each.value[0]
  destination_cidr_block = each.value[1]
  transit_gateway_id     = aws_ec2_transit_gateway.this.id

  depends_on = [aws_ec2_transit_gateway_vpc_attachment.shared]
}

resource "aws_route" "cluster_to_remote" {
  for_each = {
    for pair in setproduct(local.cluster_route_table_ids, local.remote_cidrs) : "${pair[0]}|${pair[1]}" => pair
  }

  route_table_id         = each.value[0]
  destination_cidr_block = each.value[1]
  transit_gateway_id     = aws_ec2_transit_gateway.this.id

  depends_on = [aws_ec2_transit_gateway_vpc_attachment.cluster]
}
