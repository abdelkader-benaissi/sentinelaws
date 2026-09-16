terraform {
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.70, < 7.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = ">= 2.6, < 3.0"
    }
  }
}
