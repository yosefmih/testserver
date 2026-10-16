output "id" {
  value = aws_ec2_transit_gateway.this.id
}

output "asn" {
  value = aws_ec2_transit_gateway.this.amazon_side_asn
}

output "route_table_id" {
  value = aws_ec2_transit_gateway.this.association_default_route_table_id
}

output "shared_vpc_attachment_id" {
  value = aws_ec2_transit_gateway_vpc_attachment.shared.id
}
