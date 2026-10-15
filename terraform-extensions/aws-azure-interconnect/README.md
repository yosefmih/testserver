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

`porter.tf` declares where the extension acts: the AWS account and region with the shared VPC, and the Azure
subscription and location with the AKS clusters, by their Porter cloud account IDs, and the AKS clusters by
their Porter cluster IDs. Porter configures the `aws` and `azurerm` providers for those two accounts and passes
the outputs of its stacks there in `var.porter`. Edit `porter.tf` to point it at your own accounts, region,
location and clusters.

## Register it

Prerequisites: an applied regional backbone in the AWS region, and AKS clusters created with
"Create the network with Terraform" in one Azure location.

Infrastructure → Terraform → Extensions → New extension: pick the repository and branch, then this folder.
Porter reads the scopes from `porter.tf` and grants the extension the two cloud accounts it declares.

Optional, as variable defaults in `variables.tf`: `hub_vnet_cidr` (default `100.127.0.0/24`; must not overlap
the VPC or the AKS VNets) and `datastore_security_groups`, as `{ "sg-0123456789abcdef0" = 5432 }`.

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
    "repo_owner": "<owner>", "repo_name": "<repo>", "ref": "main",
    "path": "terraform-extensions/aws-azure-interconnect"
  }'
```
