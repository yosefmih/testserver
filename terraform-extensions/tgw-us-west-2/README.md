# Transit gateway for Porter's us-west-2 network

A Porter Terraform extension. It creates a transit gateway and attaches the two VPCs Porter's
Terraform stacks manage in us-west-2: the shared VPC (`region/us-west-2`) and cluster 21's VPC
(`cluster/21`). Optionally it routes `remote_cidrs` from both VPCs through the transit gateway,
which is how a VPN or another VPC would later be reached.

It only adds resources next to Porter's: its own transit gateway and attachments, plus separate
route entries in Porter's route tables. The two VPCs keep talking over Porter's peering; the
transit gateway does not replace it.

## Register it

Extensions → New extension:

- Repository: `yosefmih/testserver`, ref `main`, path `terraform-extensions/tgw-us-west-2`
- Upstream stacks, in this order: `region/us-west-2`, `cluster/21`
- Variables:

  ```json
  {"region_stack": "region/us-west-2", "cluster_stack": "cluster/21", "remote_cidrs": []}
  ```

To route a remote network through the transit gateway, add it to `remote_cidrs` and to the
extension's external CIDRs, e.g. `10.200.0.0/16`. Porter refuses ranges that overlap its own.
