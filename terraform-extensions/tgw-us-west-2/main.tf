locals {
  region         = "us-west-2"
  shared_network = var.porter.stacks.regional_backbones[local.region]
  clusters       = { for id, cluster in var.porter.stacks.clusters : id => cluster if cluster.region == local.region }
}

resource "aws_ec2_transit_gateway" "this" {
  description                     = "Connects Porter's shared VPC and cluster VPCs in ${local.region}"
  default_route_table_association = "enable"
  default_route_table_propagation = "enable"
  dns_support                     = "enable"

  tags = {
    Name = "porter-extension-tgw"
  }
}

# A transit gateway attachment takes one subnet per availability zone
resource "aws_ec2_transit_gateway_vpc_attachment" "shared" {
  transit_gateway_id = aws_ec2_transit_gateway.this.id
  vpc_id             = local.shared_network.vpc_id
  subnet_ids         = [for subnet in local.shared_network.subnets : subnet.id if subnet.service == "customer"]

  tags = {
    Name = "porter-extension-tgw-shared"
  }
}

resource "aws_ec2_transit_gateway_vpc_attachment" "cluster" {
  for_each = local.clusters

  transit_gateway_id = aws_ec2_transit_gateway.this.id
  vpc_id             = each.value.vpc_id
  subnet_ids         = [for subnet in each.value.private_subnets : subnet.id]

  tags = {
    Name = "porter-extension-tgw-cluster-${each.key}"
  }
}
