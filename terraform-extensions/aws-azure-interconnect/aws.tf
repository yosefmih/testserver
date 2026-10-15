resource "aws_ec2_transit_gateway" "hub" {
  region                          = local.aws.region
  description                     = local.name
  amazon_side_asn                 = local.transit_gateway_asn
  vpn_ecmp_support                = "enable"
  default_route_table_association = "enable"
  default_route_table_propagation = "enable"
  dns_support                     = "enable"

  tags = { Name = local.name }
}

resource "aws_ec2_transit_gateway_vpc_attachment" "shared" {
  region             = local.aws.region
  transit_gateway_id = aws_ec2_transit_gateway.hub.id
  vpc_id             = local.aws.shared_network.vpc.id
  subnet_ids         = [for subnet in values(local.datastore_subnets) : subnet.id]

  tags = { Name = "${local.name}-shared" }
}
