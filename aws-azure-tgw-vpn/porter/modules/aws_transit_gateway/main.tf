resource "aws_ec2_transit_gateway" "this" {
  description                     = var.name
  amazon_side_asn                 = var.asn
  vpn_ecmp_support                = "enable"
  default_route_table_association = "enable"
  default_route_table_propagation = "enable"
  dns_support                     = "enable"

  tags = { Name = var.name }
}

resource "aws_ec2_transit_gateway_vpc_attachment" "shared" {
  transit_gateway_id = aws_ec2_transit_gateway.this.id
  vpc_id             = var.shared_vpc_id
  subnet_ids         = var.shared_vpc_attachment_subnet_ids

  tags = { Name = "${var.name}-shared" }
}
