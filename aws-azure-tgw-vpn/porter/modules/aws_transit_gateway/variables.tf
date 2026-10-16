variable "name" {
  description = "Name of the transit gateway and prefix of its attachments"
  type        = string
}

variable "asn" {
  description = "BGP ASN of the transit gateway"
  type        = number
  default     = 64512
}

variable "shared_vpc_id" {
  description = "Regional shared VPC to attach"
  type        = string
}

variable "shared_vpc_attachment_subnet_ids" {
  description = "One shared VPC subnet per availability zone for the attachment ENIs"
  type        = list(string)
}
