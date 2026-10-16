# Infrastructure

This repository holds the Terraform for cloud account `992382605253` (AWS). Porter created it and keeps
`porter/` up to date; `custom/` is yours.

```
porter/                     # written by Porter; do not edit
  modules/                  #   the modules Porter's stacks are built from
  regions/us-west-2/        #   the regional backbone: shared VPC, subnets, route tables
  clusters/21/              #   cluster 21's VPC, NAT, peering with the regional backbone
  outputs/                  #   module that exposes every Porter stack's outputs
custom/                     # yours
  tgw/                      #   a transit gateway attached to Porter's VPCs
.github/workflows/porter.yml
```

Every directory under `porter/regions`, `porter/clusters` and `custom` is its own Terraform root with its
own state, so one stack's change never waits on, or breaks, another's. State lives in the S3 bucket
`porter-tf-state-992382605253` in this account, with S3 locking, shared by Porter and by you.

## How changes apply

- **Porter's changes:** when you change a cluster or region in Porter, Porter commits the new Terraform to
  `porter/` and applies it.
- **Your changes:** open a pull request touching `custom/`. The workflow asks Porter for a plan of every
  stack it touches. Merge, and Porter runs the plan again and waits for your approval in the dashboard
  before applying.
- Porter runs Terraform in a CodeBuild project in this account, so your code runs in your account with
  the role you granted Porter.

## Using Porter's outputs

```hcl
module "porter" {
  source = "../../porter/outputs"
}

module.porter.regional_backbones["us-west-2"].vpc_id
module.porter.clusters["21"].private_subnets
```

Set your own `provider "aws"` region; when a stack does not set one, Porter runs it in `us-east-1`.

## Working locally

It is ordinary Terraform. With credentials for this account:

```sh
cd custom/tgw
terraform init
terraform plan
terraform state list
terraform import aws_ec2_transit_gateway.this tgw-0123456789abcdef0
```

Porter takes the same S3 lock, so a local operation and a Porter run never overlap. Avoid applying
changes to `porter/` stacks by hand; Porter's next run puts them back to what Porter rendered.
