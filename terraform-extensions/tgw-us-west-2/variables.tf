# Porter passes the latest applied outputs of each upstream stack as var.porter.stacks["<stack>"]
variable "porter" {
  type = any
}

# The extension's own settings, from the extension's variables:
#   region_stack  Porter region stack whose shared VPC is attached, e.g. "region/us-west-2"
#   cluster_stack Porter cluster stack whose VPC is attached, e.g. "cluster/21"
#   remote_cidrs  networks reached through the transit gateway, e.g. a VPN or another VPC; routes to
#                 them are added to both VPCs. They must be registered as the extension's external CIDRs.
variable "inputs" {
  type = any
}
