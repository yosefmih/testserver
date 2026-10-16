data "aws_availability_zones" "available" {
  state = "available"

  filter {
    name   = "opt-in-status"
    values = ["opt-in-not-required"]
  }
}

locals {
  availability_zones = slice(sort(data.aws_availability_zones.available.names), 0, var.availability_zone_count)
  zone_index         = { for index, zone in local.availability_zones : zone => index }

  cluster_tag_key      = "kubernetes.io/cluster/${var.cluster_name}"
  capa_cluster_tag_key = "sigs.k8s.io/cluster-api-provider-aws/cluster/${var.cluster_name}"

  common_tags = {
    "porter.run/managed"    = "true"
    "porter.run/cluster-id" = tostring(var.cluster_id)
  }
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(local.common_tags, {
    Name                         = "${var.cluster_name}-vpc"
    (local.capa_cluster_tag_key) = "shared"
  })

  # tags are set at creation; tags customers or CAPA add later are left alone
  lifecycle {
    ignore_changes = [tags]
  }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = merge(local.common_tags, {
    Name = "${var.cluster_name}-igw"
  })

  # tags are set at creation; tags customers or CAPA add later are left alone
  lifecycle {
    ignore_changes = [tags]
  }
}

# Public subnets take the first three /20s; private subnets take the last three /18s.
resource "aws_subnet" "public" {
  for_each = local.zone_index

  vpc_id                  = aws_vpc.this.id
  availability_zone       = each.key
  cidr_block              = cidrsubnet(var.vpc_cidr, 4, each.value)
  map_public_ip_on_launch = true

  tags = merge(local.common_tags, {
    Name                                        = "${var.cluster_name}-subnet-public-${each.key}"
    "kubernetes.io/role/elb"                    = "1"
    "sigs.k8s.io/cluster-api-provider-aws/role" = "public"
    (local.cluster_tag_key)                     = "shared"
    (local.capa_cluster_tag_key)                = "shared"
  })

  # tags are set at creation; tags customers or CAPA add later are left alone
  lifecycle {
    ignore_changes = [tags]
  }
}

resource "aws_subnet" "private" {
  for_each = local.zone_index

  vpc_id            = aws_vpc.this.id
  availability_zone = each.key
  cidr_block        = cidrsubnet(var.vpc_cidr, 2, each.value + 1)

  tags = merge(local.common_tags, {
    Name                                        = "${var.cluster_name}-subnet-private-${each.key}"
    "kubernetes.io/role/internal-elb"           = "1"
    "sigs.k8s.io/cluster-api-provider-aws/role" = "private"
    (local.cluster_tag_key)                     = "shared"
    (local.capa_cluster_tag_key)                = "shared"
  })

  # tags are set at creation; tags customers or CAPA add later are left alone
  lifecycle {
    ignore_changes = [tags]
  }
}

resource "aws_eip" "nat" {
  for_each = local.zone_index

  domain = "vpc"

  tags = merge(local.common_tags, {
    Name = "${var.cluster_name}-eip-nat-${each.key}"
  })

  # tags are set at creation; tags customers or CAPA add later are left alone
  lifecycle {
    ignore_changes = [tags]
  }
}

resource "aws_nat_gateway" "this" {
  for_each = local.zone_index

  allocation_id = aws_eip.nat[each.key].id
  subnet_id     = aws_subnet.public[each.key].id

  tags = merge(local.common_tags, {
    Name = "${var.cluster_name}-nat-${each.key}"
  })

  # tags are set at creation; tags customers or CAPA add later are left alone
  lifecycle {
    ignore_changes = [tags]
  }

  depends_on = [aws_internet_gateway.this]
}

# Routes are separate resources, never inline blocks, so routes added outside this
# module (peering, transit gateways, customer additions) survive every apply.
resource "aws_route_table" "public" {
  for_each = local.zone_index

  vpc_id = aws_vpc.this.id

  tags = merge(local.common_tags, {
    Name = "${var.cluster_name}-rt-public-${each.key}"
  })

  # tags are set at creation; tags customers or CAPA add later are left alone
  lifecycle {
    ignore_changes = [tags]
  }
}

resource "aws_route" "public_internet" {
  for_each = local.zone_index

  route_table_id         = aws_route_table.public[each.key].id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

resource "aws_route_table_association" "public" {
  for_each = local.zone_index

  subnet_id      = aws_subnet.public[each.key].id
  route_table_id = aws_route_table.public[each.key].id
}

resource "aws_route_table" "private" {
  for_each = local.zone_index

  vpc_id = aws_vpc.this.id

  tags = merge(local.common_tags, {
    Name = "${var.cluster_name}-rt-private-${each.key}"
  })

  # tags are set at creation; tags customers or CAPA add later are left alone
  lifecycle {
    ignore_changes = [tags]
  }
}

resource "aws_route" "private_nat" {
  for_each = local.zone_index

  route_table_id         = aws_route_table.private[each.key].id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.this[each.key].id
}

resource "aws_route_table_association" "private" {
  for_each = local.zone_index

  subnet_id      = aws_subnet.private[each.key].id
  route_table_id = aws_route_table.private[each.key].id
}

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"

  tags = merge(local.common_tags, {
    Name = "${var.cluster_name}-vpce-s3"
  })

  # tags are set at creation; tags customers or CAPA add later are left alone
  lifecycle {
    ignore_changes = [tags]
  }
}

resource "aws_vpc_endpoint_route_table_association" "s3_private" {
  for_each = local.zone_index

  vpc_endpoint_id = aws_vpc_endpoint.s3.id
  route_table_id  = aws_route_table.private[each.key].id
}
