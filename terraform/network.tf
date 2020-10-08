#
# VPC and basic networking
#

module "loc_network_configuration" {
  source = "git::https://git.loc.gov/DevOps/terraform/lc-network-configuration-data.git?ref=v2.2.0"
}

resource "aws_eip" "nat" {
  count = 1
  vpc   = true
}

module "vpc" {
  source                     = "terraform-aws-modules/vpc/aws"
  version                    = "~> 2.50"
  name                       = "${local.project_name}-${local.environment}"
  tags                       = local.tags
  azs                        = slice(sort(data.aws_availability_zones.available.names), 0, 2)
  cidr                       = local.vpc_cidr_allocation
  public_subnets             = cidrsubnets(local.public_cidr, 2, 2)
  private_subnets            = cidrsubnets(local.private_cidr, 2, 2)
  enable_nat_gateway         = true
  single_nat_gateway         = true
  reuse_nat_ips              = true
  external_nat_ip_ids        = aws_eip.nat.*.id
  one_nat_gateway_per_az     = true
  enable_dns_hostnames       = true
  enable_dns_support         = true
  enable_vpn_gateway         = true
  manage_default_network_acl = true
  default_network_acl_name   = "${local.deployment_id}-default"
  nat_eip_tags               = merge({ "Name" = "${local.deployment_id} NAT Gateway" }, local.tags)
  igw_tags                   = merge({ "Name" = "${local.deployment_id} Public Internet Gateway" }, local.tags)

  # Leaving these as empty lists will result in no rules being applied, leaving
  # the AWS default deny-all rules:
  default_network_acl_ingress = []
  default_network_acl_egress  = []

  public_dedicated_network_acl  = true
  private_dedicated_network_acl = true

  public_inbound_acl_rules = [
    for i in range(length(module.loc_network_configuration.default_ingress_acls)) :
    merge(
      {
        rule_number = 1000 + i,
        rule_action = module.loc_network_configuration.default_ingress_acls[i]["action"]
      },
      module.loc_network_configuration.default_ingress_acls[i]
    )
  ]

  public_outbound_acl_rules = [
    for i in range(length(module.loc_network_configuration.default_egress_acls)) :
    merge(
      {
        rule_number = 1000 + i,
        rule_action = module.loc_network_configuration.default_egress_acls[i]["action"]
      },
      module.loc_network_configuration.default_egress_acls[i]
    )
  ]

  private_inbound_acl_rules = concat(
    [
      for i in range(length(module.loc_network_configuration.core_icmp_acls)) :
      merge(
        module.loc_network_configuration.core_icmp_acls[i],
        {
          rule_number = 500 + i,
          rule_action = module.loc_network_configuration.core_icmp_acls[i]["action"],
        }
      )
    ],
    [
      { rule_number = 1000, rule_action = "allow", from_port = 80, to_port = 80, protocol = "tcp", cidr_block = local.vpc_cidr_allocation },
      { rule_number = 1001, rule_action = "allow", from_port = 443, to_port = 443, protocol = "tcp", cidr_block = local.vpc_cidr_allocation },
      { rule_number = 1002, rule_action = "allow", from_port = 1024, to_port = 65535, protocol = "tcp", cidr_block = "0.0.0.0/0" },
    ],
  )

  private_outbound_acl_rules = concat(
    [
      # Portmap:
      { rule_number = 500, rule_action = "allow", protocol = "udp", from_port = 111, to_port = 111, cidr_block = local.vpc_cidr_allocation },
      { rule_number = 501, rule_action = "allow", protocol = "tcp", from_port = 111, to_port = 111, cidr_block = local.vpc_cidr_allocation },
      # NFS:
      { rule_number = 510, rule_action = "allow", protocol = "udp", from_port = 2049, to_port = 2049, cidr_block = local.vpc_cidr_allocation },
      { rule_number = 511, rule_action = "allow", protocol = "tcp", from_port = 2049, to_port = 2049, cidr_block = local.vpc_cidr_allocation },
      # NFS v3:
      { rule_number = 520, rule_action = "allow", protocol = "udp", from_port = 20048, to_port = 20048, cidr_block = local.vpc_cidr_allocation },
      { rule_number = 521, rule_action = "allow", protocol = "tcp", from_port = 20048, to_port = 20048, cidr_block = local.vpc_cidr_allocation },
    ],
    [
      for i in range(length(module.loc_network_configuration.minimal_egress_acls)) :
      merge(
        {
          rule_number = 1000 + i,
          rule_action = module.loc_network_configuration.minimal_egress_acls[i]["action"]
        },
        module.loc_network_configuration.minimal_egress_acls[i]
      )
    ]
  )


}

# Add Transit Gateway routes to public and private route tables

resource "aws_ec2_transit_gateway_vpc_attachment" "loc_tgw" {
  vpc_id             = module.vpc.vpc_id
  transit_gateway_id = var.loc_transit_gateway_id
  subnet_ids         = module.vpc.public_subnets
  tags               = local.tags
}

locals {
  # We want to ensure that every route table has routes through the Transit
  # Gateway for the Library network and the other AWS resources. Since the
  # Terraform for_each syntax does not support nested iteration and requires its
  # inputs to either be a set of strings (not tuples) or a map, we will generate
  # a map containing the product of our list of route tables and the target CIDR
  # blocks:
  all_route_tables = concat(module.vpc.public_route_table_ids, module.vpc.private_route_table_ids)
  # tgw_cidrs        = concat(module.loc_network_configuration.loc_aws_transit_gateway_cidr, module.loc_network_configuration.loc_ipv4_cidr)
  tgw_cidrs = module.loc_network_configuration.loc_aws_transit_gateway_cidr
  all_routes = {
    for pair in setproduct(local.all_route_tables, local.tgw_cidrs) :
    "${pair[0]}-${pair[1]}" => pair
  }
}

resource "aws_route" "loc_tgw_peers" {
  for_each               = local.all_routes
  route_table_id         = each.value[0]
  destination_cidr_block = each.value[1]
  transit_gateway_id     = aws_ec2_transit_gateway_vpc_attachment.loc_tgw.transit_gateway_id
}
