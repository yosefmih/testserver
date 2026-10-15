# AWS shared VPC ↔ AKS over a transit gateway VPN

A Porter Terraform extension. It connects an AWS region's shared VPC (Porter's regional backbone) to
AKS clusters whose VNets Porter's Terraform backbone created, over an active-active, BGP-routed
IPsec VPN:

```
 shared VPC ── TGW ══ 2 VPN connections × 2 tunnels ══ active-active VPN gateway (hub VNet) ── AKS VNet
 (rds subnets route AKS VNets to the TGW)                                     (peering, gateway transit)
```

It creates the transit gateway and its shared VPC attachment, the Azure hub resource group, VNet
and VPN gateway, the four tunnels, the hub ↔ AKS VNet peerings, routes to each AKS VNet in the shared
VPC's datastore route tables, and optional ingress rules on datastore security groups.

The extension belongs to the project and acts in the two cloud accounts named when it is registered: the
AWS account with the regional backbone and the Azure subscription with the AKS clusters' Terraform stacks.
Porter configures the `aws` and `azurerm` providers for those accounts and passes their stack outputs in
`var.porter`.

## Register it

Prerequisites: an applied regional backbone in the AWS account, and AKS clusters created with
"Create the network with Terraform" in one Azure location.

Infrastructure → Terraform → Extensions → New extension:

- Cloud accounts: the AWS account and the Azure subscription
- Repository: the repo holding this directory, path `terraform-extensions/aws-azure-interconnect`
- Variables:

```json
{
  "aks_cluster_ids": ["<porter cluster id>"],
  "datastore_security_groups": { "sg-0123456789abcdef0": 5432 }
}
```

Optional: `aws_region` (default: the first regional backbone by name) and `hub_vnet_cidr` (default
`100.127.0.0/24`; must not overlap the VPC or the AKS VNets).

The first apply takes 30 to 45 minutes; the Azure VPN gateway is most of it.

## Verify

```sh
aws ec2 describe-vpn-connections --region <region> \
  --query 'VpnConnections[].VgwTelemetry[].[OutsideIpAddress,Status,StatusMessage]'
az network vnet-gateway list-bgp-peer-status -g <name>-hub -n <name>-vpngw -o table
```

where `<name>` is `aws-<region>--azure-<location>`. Then from an AKS pod, reach a datastore in the
shared VPC by its private address.

Through the API, the same registration is:

```sh
curl -X POST "$PORTER_URL/api/v2/projects/<project id>/terraform/extensions" \
  -H "Authorization: Bearer $PORTER_TOKEN" -H 'Content-Type: application/json' -d '{
    "name": "aws-azure-interconnect",
    "cloud_account_ids": ["<aws cloud account id>", "<azure cloud account id>"],
    "git_installation_id": <installation id>,
    "repo_owner": "<owner>", "repo_name": "<repo>", "ref": "main",
    "path": "terraform-extensions/aws-azure-interconnect",
    "variables": { "aks_cluster_ids": ["<porter cluster id>"] }
  }'
```
