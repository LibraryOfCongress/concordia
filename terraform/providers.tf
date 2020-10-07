provider "aws" {
  region = var.region
}

# Using a single workspace:
terraform {
  backend "remote" {
    hostname     = "app.terraform.io"
    organization = "loc"

    workspaces {
      prefix = "crowd-concordia-"
    }
  }
}
