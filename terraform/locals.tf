locals {
  project_name  = "Crowd-Concordia"
  environment   = lower(terraform.workspace)
  deployment_id = "${local.project_name}-${local.environment}"

  environments_long = {
    "dev"   = "Development",
    "test"  = "Testing",
    "stage" = "Staging",
    "prod"  = "Production"
  }

  environment_long = local.environments_long[local.environment]

  # Common tags to be assigned to all resources
  tags = merge(
    {
      "Project"     = local.project_name
      "Application" = "Concordia"
      "Environment" = local.environment_long,
      "Terraform"   = "true",
      "Workspace"   = "crowd-concordia-${lower(local.environment)}",
      "Creator"     = var.creator
    },
    var.tags
  )

  vpc_cidr_allocations = {
    "dev"   = "10.192.0.0/16",
    "test"  = "10.193.0.0/16",
    "stage" = "10.194.0.0/16",
    "prod"  = "10.195.0.0/16"
  }

  vpc_cidr_allocation = local.vpc_cidr_allocations[local.environment]

  certificate_arns = {
    "dev"   = "arn:aws:iam::619333082511:server-certificate/crowd-dev.loc.gov",
    "test"  = "arn:aws:acm:us-east-1:619333082511:certificate/c33e73b9-d5f4-4b37-813c-033ee2e04e3c",
    "stage" = "arn:aws:iam::619333082511:server-certificate/crowd-stage.loc.gov",
    "prod"  = "arn:aws:iam::619333082511:server-certificate/crowd-prod.loc.gov"
  }
  certificate_arn = local.certificate_arns[local.environment]

  public_cidr  = cidrsubnet(local.vpc_cidr_allocation, 1, 0)
  private_cidr = cidrsubnet(local.vpc_cidr_allocation, 1, 1)
}
