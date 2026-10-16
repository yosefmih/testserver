variable "cluster_name" {
  description = "Name of the EKS cluster whose VPC is peered"
  type        = string
}

variable "cluster_id" {
  description = "Porter ID of the cluster"
  type        = number
}

variable "cluster_vpc_id" {
  description = "ID of the cluster VPC"
  type        = string
}

variable "cluster_vpc_cidr" {
  description = "CIDR block of the cluster VPC"
  type        = string
}

variable "cluster_route_table_ids" {
  description = "Every route table of the cluster VPC"
  type        = list(string)
}

variable "shared_vpc_id" {
  description = "ID of the region's shared VPC"
  type        = string
}

variable "shared_vpc_cidr" {
  description = "CIDR block of the region's shared VPC"
  type        = string
}

variable "shared_route_table_ids" {
  description = "Every route table of the shared VPC, by subnet name"
  type        = map(string)
}
