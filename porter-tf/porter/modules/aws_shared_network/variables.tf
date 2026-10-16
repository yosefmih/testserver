variable "region" {
  description = "AWS region of the shared VPC"
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block of the shared VPC; must be a /16"
  type        = string

  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0)) && tonumber(split("/", var.vpc_cidr)[1]) == 16
    error_message = "vpc_cidr must be a valid /16 CIDR block."
  }
}

variable "availability_zone_count" {
  description = "Number of availability zones to spread subnets across"
  type        = number
  default     = 3
}
