output "aws_regional_backbones" {
  description = "Each AWS region's shared network and transit gateway, by region"
  value = {
    "us-west-2" = data.terraform_remote_state.aws_992382605253_us_west_2.outputs
  }
}

output "azure_regional_backbones" {
  description = "Each Azure region's VPN hub, by region"
  value = {
    "eastus" = data.terraform_remote_state.azure_d3b9d70c_74c7_4d50_a2cc_579bf51dc763_eastus.outputs
  }
}
