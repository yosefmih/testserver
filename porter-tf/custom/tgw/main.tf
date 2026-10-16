# Customer-owned. Porter never edits anything under custom/; changes here wait for approval in Porter.
#
# A transit gateway attached to Porter's shared VPC and every cluster VPC in us-west-2.

terraform {
  required_version = ">= 1.9"

  backend "s3" {
    bucket       = "porter-tf-state-992382605253"
    key          = "custom/tgw/terraform.tfstate"
    region       = "us-east-1"
    use_lockfile = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = "us-west-2"
}

module "porter" {
  source = "../../porter/outputs"
}

locals {
  shared_network = module.porter.regional_backbones["us-west-2"]
  clusters       = { for id, cluster in module.porter.clusters : id => cluster if cluster.region == "us-west-2" }
}

resource "aws_ec2_transit_gateway" "this" {
  description                     = "Connects Porter's shared VPC and cluster VPCs in us-west-2"
  default_route_table_association = "enable"
  default_route_table_propagation = "enable"
  dns_support                     = "enable"

  tags = {
    Name = "acme-tgw"
  }
}

# A transit gateway attachment takes one subnet per availability zone
resource "aws_ec2_transit_gateway_vpc_attachment" "shared" {
  transit_gateway_id = aws_ec2_transit_gateway.this.id
  vpc_id             = local.shared_network.vpc_id
  subnet_ids         = [for subnet in local.shared_network.subnets : subnet.id if subnet.service == "customer"]

  tags = {
    Name = "acme-tgw-shared"
  }
}

resource "aws_ec2_transit_gateway_vpc_attachment" "cluster" {
  for_each = local.clusters

  transit_gateway_id = aws_ec2_transit_gateway.this.id
  vpc_id             = each.value.vpc_id
  subnet_ids         = [for subnet in each.value.private_subnets : subnet.id]

  tags = {
    Name = "acme-tgw-cluster-${each.key}"
  }
}

output "transit_gateway_id" {
  value = aws_ec2_transit_gateway.this.id
}
