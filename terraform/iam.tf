# One role per function, each with only what that function needs.

data "aws_iam_policy_document" "lambda_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# --- scanner: read-only on EC2, write to its own table and topic -----------

resource "aws_iam_role" "scanner" {
  name               = "${local.scanner_name}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

data "aws_iam_policy_document" "scanner" {
  statement {
    sid = "ReadInventory"
    # EC2 Describe calls and CloudWatch reads don't support resource-level
    # permissions, so "*" is the only option here. They're all read-only.
    actions = [
      "ec2:DescribeInstances",
      "ec2:DescribeVolumes",
      "ec2:DescribeSnapshots",
      "ec2:DescribeImages",
      "ec2:DescribeAddresses",
      "cloudwatch:GetMetricStatistics",
    ]
    resources = ["*"]
  }

  statement {
    sid       = "FindingsHistory"
    actions   = ["dynamodb:Query", "dynamodb:PutItem", "dynamodb:BatchWriteItem"]
    resources = [aws_dynamodb_table.findings.arn]
  }

  statement {
    sid       = "SendReport"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.alerts.arn]
  }

  statement {
    sid       = "OwnLogsOnly"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.scanner.arn}:*"]
  }
}

resource "aws_iam_role_policy" "scanner" {
  name   = "least-privilege"
  role   = aws_iam_role.scanner.id
  policy = data.aws_iam_policy_document.scanner.json
}

# --- scheduler Lambda: can only start/stop instances that carry the tag ----

resource "aws_iam_role" "scheduler_lambda" {
  name               = "${local.scheduler_name}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

data "aws_iam_policy_document" "scheduler_lambda" {
  statement {
    sid       = "FindInstances"
    actions   = ["ec2:DescribeInstances"]
    resources = ["*"]
  }

  statement {
    sid       = "StartStopTaggedOnly"
    actions   = ["ec2:StartInstances", "ec2:StopInstances"]
    resources = ["arn:aws:ec2:*:${data.aws_caller_identity.current.account_id}:instance/*"]

    # Even if the code had a bug and passed a production instance ID,
    # IAM would refuse it unless that instance has the tag.
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/${var.schedule_tag_key}"
      values   = [var.schedule_tag_value]
    }
  }

  statement {
    sid       = "OwnLogsOnly"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.scheduler.arn}:*"]
  }
}

resource "aws_iam_role_policy" "scheduler_lambda" {
  name   = "least-privilege"
  role   = aws_iam_role.scheduler_lambda.id
  policy = data.aws_iam_policy_document.scheduler_lambda.json
}

# --- EventBridge Scheduler: allowed to invoke these two functions, nothing else

data "aws_iam_policy_document" "eventbridge_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_iam_role" "eventbridge" {
  name               = "${var.project}-eventbridge-role"
  assume_role_policy = data.aws_iam_policy_document.eventbridge_trust.json
}

data "aws_iam_policy_document" "eventbridge" {
  statement {
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.scanner.arn, aws_lambda_function.scheduler.arn]
  }
}

resource "aws_iam_role_policy" "eventbridge" {
  name   = "invoke-watchdog-functions"
  role   = aws_iam_role.eventbridge.id
  policy = data.aws_iam_policy_document.eventbridge.json
}
