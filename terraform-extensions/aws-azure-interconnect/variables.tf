# Porter passes the outputs of every Porter stack in the cloud accounts the extension acts in:
#   var.porter.stacks.regional_backbones["<region>"] is an AWS region's shared network
#   var.porter.stacks.clusters["<cluster id>"] is an AWS or Azure cluster's network
variable "porter" {
  type = any
}

# Porter passes the extension's variables here:
#   aks_cluster_ids            Porter IDs of the AKS clusters to connect; required, all in one Azure location
#   aws_region                 regional backbone to connect; defaults to the first by name
#   hub_vnet_cidr              address space of the Azure hub VNet; defaults to 100.127.0.0/24
#   datastore_security_groups  security groups that admit the AKS clusters, as { "<sg id>" = <port> }; defaults to none
variable "inputs" {
  type = any
}
