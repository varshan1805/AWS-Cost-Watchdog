terraform {
  # 1.10+ for S3 state locking without a DynamoDB lock table
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.6"
    }
  }

  # Bucket and key come from backend.hcl (see backend.hcl.example), so the
  # account-specific bucket name isn't hard-coded in the repo.
  backend "s3" {}
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = var.project
      ManagedBy = "terraform"
    }
  }
}
