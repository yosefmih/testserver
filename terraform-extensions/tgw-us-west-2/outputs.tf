output "transit_gateway_id" {
  value = aws_ec2_transit_gateway.this.id
}

output "transit_gateway_route_table_id" {
  value = aws_ec2_transit_gateway.this.association_default_route_table_id
}

output "attachment_ids" {
  value = {
    shared  = aws_ec2_transit_gateway_vpc_attachment.shared.id
    cluster = aws_ec2_transit_gateway_vpc_attachment.cluster.id
  }
}
