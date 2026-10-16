output "vpc_id" {
  value = aws_vpc.this.id
}

output "vpc_cidr" {
  value = aws_vpc.this.cidr_block
}

output "subnets" {
  value = [
    for name, subnet in local.subnets : {
      id                = aws_subnet.this[name].id
      name              = name
      service           = subnet.service
      availability_zone = subnet.availability_zone
      cidr              = subnet.cidr
    }
  ]
}

output "route_table_ids" {
  value = { for name, subnet in local.subnets : name => aws_route_table.this[name].id }
}
