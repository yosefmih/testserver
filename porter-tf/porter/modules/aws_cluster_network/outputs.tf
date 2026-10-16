output "vpc_id" {
  value = aws_vpc.this.id
}

output "vpc_cidr" {
  value = aws_vpc.this.cidr_block
}

output "public_subnets" {
  value = [
    for zone in local.availability_zones : {
      id                = aws_subnet.public[zone].id
      availability_zone = zone
      cidr              = aws_subnet.public[zone].cidr_block
    }
  ]
}

output "private_subnets" {
  value = [
    for zone in local.availability_zones : {
      id                = aws_subnet.private[zone].id
      availability_zone = zone
      cidr              = aws_subnet.private[zone].cidr_block
    }
  ]
}

output "nat_gateway_ips" {
  value = [for zone in local.availability_zones : aws_eip.nat[zone].public_ip]
}

output "public_route_table_ids" {
  value = [for zone in local.availability_zones : aws_route_table.public[zone].id]
}

output "private_route_table_ids" {
  value = [for zone in local.availability_zones : aws_route_table.private[zone].id]
}
