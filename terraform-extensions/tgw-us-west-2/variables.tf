# Porter passes the outputs of every Porter stack in the cloud account:
#   var.porter.stacks.regional_backbones["<region>"] is a region's shared network
#   var.porter.stacks.clusters["<cluster id>"] is a cluster's network
variable "porter" {
  type = any
}

# Porter passes the extension's variables here; this module needs none
variable "inputs" {
  type = any
}
