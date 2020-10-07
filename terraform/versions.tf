
terraform {
  required_version = ">= 0.13"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 3.6"
    }
    random = {
      source  = "hashicorp/random"
      version = "~>2.3"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~>2.2"
    }
    http = {
      source  = "hashicorp/http"
      version = "~> 1.2"
    }
  }
}
