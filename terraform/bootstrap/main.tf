# Run this once, by hand, with your own admin credentials.
# It creates the two things the main stack can't create for itself:
#   1. an S3 bucket to hold Terraform state
#   2. an IAM role GitHub Actions can assume through OIDC (no long-lived AWS keys in GitHub)
#
#   cd terraform/bootstrap
#   terraform init
#   terraform apply -var="github_repo=varshan1805/AWS-Cost-Watchdog"
#
# State for this bootstrap stays local. That's fine: it's three resources you set up once.

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  type    = string
  default = "ap-south-1"
}

variable "project" {
  type    = string
  default = "cost-watchdog"
}

variable "github_repo" {
  description = "owner/name of the GitHub repo allowed to deploy, e.g. varshan1805/AWS-Cost-Watchdog"
  type        = string
}

data "aws_caller_identity" "current" {}

locals {
  account_id   = data.aws_caller_identity.current.account_id
  state_bucket = "${var.project}-tfstate-${local.account_id}"
}

# --- state bucket ------------------------------------------------------------

resource "aws_s3_bucket" "state" {
  bucket = local.state_bucket
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled" # lets you roll back a broken state file
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    id     = "expire-old-state-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}

# --- GitHub OIDC -------------------------------------------------------------

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  # AWS no longer checks this thumbprint for GitHub's provider, but the API still wants one
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

data "aws_iam_policy_document" "github_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    # Only workflows from this repo's main branch can deploy. Forks and PR branches can't.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo}:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "deploy" {
  name                 = "${var.project}-github-deploy"
  assume_role_policy   = data.aws_iam_policy_document.github_trust.json
  max_session_duration = 3600
}

# Scoped to resources named with the project prefix wherever the service allows it
data "aws_iam_policy_document" "deploy" {
  statement {
    sid     = "TerraformState"
    actions = ["s3:ListBucket", "s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = [
      aws_s3_bucket.state.arn,
      "${aws_s3_bucket.state.arn}/*",
    ]
  }

  statement {
    sid       = "Lambda"
    actions   = ["lambda:*"]
    resources = ["arn:aws:lambda:*:${local.account_id}:function:${var.project}-*"]
  }

  statement {
    sid       = "ProjectRoles"
    actions   = ["iam:*Role", "iam:*RolePolicy", "iam:*RolePolicies", "iam:ListInstanceProfilesForRole", "iam:ListRoleTags", "iam:TagRole", "iam:UntagRole", "iam:PassRole"]
    resources = ["arn:aws:iam::${local.account_id}:role/${var.project}-*"]
  }

  statement {
    sid       = "Logs"
    actions   = ["logs:*"]
    resources = ["arn:aws:logs:*:${local.account_id}:log-group:/aws/lambda/${var.project}-*"]
  }

  statement {
    sid       = "LogsDescribe"
    actions   = ["logs:DescribeLogGroups", "logs:ListTagsForResource"]
    resources = ["*"]
  }

  statement {
    sid       = "DynamoDB"
    actions   = ["dynamodb:*"]
    resources = ["arn:aws:dynamodb:*:${local.account_id}:table/${var.project}-*"]
  }

  statement {
    sid       = "SNS"
    actions   = ["sns:*"]
    resources = ["arn:aws:sns:*:${local.account_id}:${var.project}-*"]
  }

  statement {
    sid     = "Scheduler"
    actions = ["scheduler:*"]
    resources = [
      "arn:aws:scheduler:*:${local.account_id}:schedule-group/${var.project}",
      "arn:aws:scheduler:*:${local.account_id}:schedule/${var.project}/*",
    ]
  }

  statement {
    sid       = "Alarms"
    actions   = ["cloudwatch:PutMetricAlarm", "cloudwatch:DeleteAlarms", "cloudwatch:DescribeAlarms", "cloudwatch:ListTagsForResource", "cloudwatch:TagResource"]
    resources = ["arn:aws:cloudwatch:*:${local.account_id}:alarm:${var.project}-*"]
  }

  statement {
    sid       = "Budgets"
    actions   = ["budgets:ViewBudget", "budgets:ModifyBudget", "budgets:ListTagsForResource", "budgets:TagResource"]
    resources = ["arn:aws:budgets::${local.account_id}:budget/${var.project}-*"]
  }

  statement {
    sid       = "WhoAmI"
    actions   = ["sts:GetCallerIdentity"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "deploy" {
  name   = "deploy-cost-watchdog"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy.json
}

output "state_bucket" {
  value = aws_s3_bucket.state.bucket
}

output "deploy_role_arn" {
  description = "Put this in the GitHub repo as the variable AWS_DEPLOY_ROLE_ARN"
  value       = aws_iam_role.deploy.arn
}
