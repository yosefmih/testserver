data "aws_availability_zones" "available" {
  state = "available"

  filter {
    name   = "opt-in-status"
    values = ["opt-in-not-required"]
  }
}

locals {
  name               = "porter-shared-${var.region}"
  availability_zones = slice(sort(data.aws_availability_zones.available.names), 0, var.availability_zone_count)

  # Datastores find their subnets by service type. Each service takes one /26 per zone, in the
  # order rds, elasticache, customer.
  subnet_prefixes = {
    rds         = "porter-shared-rds-private"
    elasticache = "porter-shared-elasticache-private"
    customer    = "porter-shared-customer-subnet"
  }
  subnets = merge([
    for service_index, service in ["rds", "elasticache", "customer"] : {
      for zone_index, zone in local.availability_zones : "${local.subnet_prefixes[service]}-${zone}" => {
        service           = service
        availability_zone = zone
        cidr              = cidrsubnet(var.vpc_cidr, 10, service_index * var.availability_zone_count + zone_index)
      }
    }
  ]...)

  managed_tags = {
    "porter.run/managed" = "true"
  }
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(local.managed_tags, {
    Name                = local.name
    "porter.run/shared" = "true"
  })

  # Datastores run in this VPC and outlive the clusters that created it.
  lifecycle {
    prevent_destroy = true
    # tags are set at creation; tags customers add later are left alone
    ignore_changes = [tags]
  }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = merge(local.managed_tags, {
    Name = "instance-proxy-${var.region}"
  })

  # tags are set at creation; tags customers or CAPA add later are left alone
  lifecycle {
    ignore_changes = [tags]
  }
}

resource "aws_subnet" "this" {
  for_each = local.subnets

  vpc_id            = aws_vpc.this.id
  availability_zone = each.value.availability_zone
  cidr_block        = each.value.cidr

  tags = merge(local.managed_tags, {
    Name                      = each.key
    "porter.run/service-type" = each.value.service
  })

  # tags are set at creation; tags customers or CAPA add later are left alone
  lifecycle {
    ignore_changes = [tags]
  }
}

# Routes are separate resources, never inline blocks, so peering routes added per cluster
# survive every apply.
resource "aws_route_table" "this" {
  for_each = local.subnets

  vpc_id = aws_vpc.this.id

  tags = merge(local.managed_tags, {
    Name = each.key
  })

  # tags are set at creation; tags customers or CAPA add later are left alone
  lifecycle {
    ignore_changes = [tags]
  }
}

resource "aws_route_table_association" "this" {
  for_each = local.subnets

  subnet_id      = aws_subnet.this[each.key].id
  route_table_id = aws_route_table.this[each.key].id
}
