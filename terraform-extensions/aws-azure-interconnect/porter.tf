locals {
  porter = {
    version = 1
    cloud_accounts = [
      { id = "641c7ef8-1ad7-4913-bd50-37218fb72755", region = "us-west-2" },
      { id = "eba066c9-0cd1-4387-b91d-ba3e5f4380cc", region = "eastus" },
    ]
    clusters = [25]
  }
}

variable "porter" {
  type = any
}
