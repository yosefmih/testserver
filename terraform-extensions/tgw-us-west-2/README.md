# Transit gateway for Porter's us-west-2 network

A Porter Terraform extension. It creates a transit gateway in us-west-2 and attaches the VPCs Porter's
Terraform stacks manage there: the region's shared VPC
(`var.porter.stacks.regional_backbones["us-west-2"]`) and every cluster VPC in the region
(`var.porter.stacks.clusters`). It needs no variables.

It only adds resources next to Porter's (its own transit gateway and attachments) and changes no route
tables, so traffic between the VPCs keeps using Porter's peering.

## Register it

Extensions → New extension:

- Repository: `yosefmih/testserver`, branch `main`, path `terraform-extensions/tgw-us-west-2`
- Variables: leave empty
