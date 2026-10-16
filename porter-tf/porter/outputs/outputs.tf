output "regional_backbones" {
  description = "Each region's shared network, by region"
  value = {
    "us-west-2" = merge(data.terraform_remote_state.region_us_west_2.outputs.shared_network, { region = "us-west-2" })
  }
}

output "clusters" {
  description = "Each cluster's network, by Porter cluster ID; a cluster whose stack has not applied yet is left out"
  value = {
    for id, cluster in {
      "21" = data.terraform_remote_state.cluster_21.outputs.network == null ? null : merge(
        data.terraform_remote_state.cluster_21.outputs.network,
        { region = "us-west-2", cluster_id = 21, cluster_name = "porter-dev4-ivy-hub" },
      )
    } : id => cluster if cluster != null
  }
}
