# AWS datastore ↔ AKS over a Transit Gateway VPN, Porter-style

A mock of how Porter would run "let AKS cluster X reach datastore Y" if all
networking were Terraform. It extends the layout in `../porter-tf/`, the
generated repo for dev account `992382605253`, to a project that spans an AWS
account and an Azure subscription.

```
porter/
  modules/
    aws_transit_gateway/      TGW + shared VPC attachment
    azure_vpn_hub/            hub VNet + active-active VPN gateway
    aws_azure_interconnect/   tunnels.tf · aks_clusters.tf · datastore_routes.tf
  aws/992382605253/regions/us-west-2/            shared VPC (porter-tf's module) + transit_gateway
  azure/d3b9d70c-…/regions/eastus/               vpn_hub
  interconnects/aws-us-west-2--azure-eastus/     interconnect: tunnels, AKS peerings, datastore routes
  outputs/                                       every stack's outputs, read via remote state
```

Three stacks, and two of them already exist in the porter-tf model. The region
stacks gain a hub module while an interconnect references them. The
interconnect is the only new stack, and the only one holding both clouds'
credentials.

## How the Go tables map

| network_hubs stack (Go) | Terraform | Who decides it exists |
|---|---|---|
| `network_hubs` row, TGW | `transit_gateway` module in the AWS region stack | Porter's render: any interconnect in the region |
| `network_hubs` row, Azure hub | `vpn_hub` module in the Azure region stack | same |
| `network_hub_tunnels` row | the interconnect stack | any datastore route between the two regions |
| `network_routes` row | one `datastore_routes` entry (+ its AKS cluster in `aks_clusters`) | the datastore ↔ cluster link |
| refcounted teardown, status jsonb | render drops the entry, `tofu apply` destroys what it owned | state |

## "Let porter-dev4-rat-net reach testdb"

The whole change is what Porter renders into the interconnect stack:

```hcl
aks_clusters = {
  "porter-dev4-rat-net" = { resource_group_name = "5-porter-dev4-rat-net", vnet_name = "porter-dev4-rat-net-vn" }
}

datastore_routes = {
  "testdb--porter-dev4-rat-net" = {
    aks_cluster                 = "porter-dev4-rat-net"
    datastore_security_group_id = "sg-…"
    datastore_port              = 5432
  }
}
```

Planning that produces the AKS VNet ↔ hub peering pair, a route to 10.137.0.0/16
in each RDS route table, and an ingress rule on testdb's security group. A
second datastore for the same cluster adds one entry and one SG rule. Removing
the entry destroys exactly those resources.

## Ordering

```
aws region stack ──┐
                   ├──▶ interconnect stack
azure region stack ┘
```

Each stack is a node, and its edges are the `module.porter` lookups it makes.
The region stacks apply in parallel; the interconnect applies once both are
done. Inside the interconnect, Terraform orders AWS VPN connections before the
Azure resources that use their tunnel IPs. Destroy runs the graph in reverse.
Porter's run orchestrator already does this for region → cluster
(`ReconcileClusterBackbone`); this adds one more edge type.

## Not modelled here

- The datastore and the AKS VNet are literals: RDS is ACK-managed and the VNet is
  CAPZ's. Porter renders their IDs from its rows, the same way porter-tf's region
  stack gets `vpc_cidr`.
- One state bucket in the AWS account holds the Azure stacks too. An
  Azure-only project would need an azurerm backend.
- Validated with `tofu validate` only. Not planned or applied against dev.
