data "aws_caller_identity" "current" {}

# boto3 ships with the Lambda Python runtime, so the package is just our own code
data "archive_file" "code" {
  type        = "zip"
  source_dir  = "${path.module}/../src"
  output_path = "${path.module}/build/watchdog.zip"
  excludes    = ["**/__pycache__/**", "**/*.pyc"]
}

locals {
  scanner_name   = "${var.project}-scanner"
  scheduler_name = "${var.project}-scheduler"

  common_env = {
    REGIONS            = join(",", var.scan_regions)
    SCHEDULE_TAG_KEY   = var.schedule_tag_key
    SCHEDULE_TAG_VALUE = var.schedule_tag_value
  }
}

# Created before the functions so Terraform owns the retention setting.
# Left to Lambda, log groups never expire and quietly cost money: the very thing this project hunts.
resource "aws_cloudwatch_log_group" "scanner" {
  name              = "/aws/lambda/${local.scanner_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "scheduler" {
  name              = "/aws/lambda/${local.scheduler_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "scanner" {
  function_name    = local.scanner_name
  description      = "Daily scan for idle and orphaned AWS resources"
  role             = aws_iam_role.scanner.arn
  runtime          = "python3.12"
  architectures    = ["arm64"] # cheaper than x86 for the same work
  handler          = "handlers.scan"
  filename         = data.archive_file.code.output_path
  source_code_hash = data.archive_file.code.output_base64sha256
  timeout          = 300
  memory_size      = 256

  environment {
    variables = merge(local.common_env, {
      FINDINGS_TABLE        = aws_dynamodb_table.findings.name
      ALERT_TOPIC_ARN       = aws_sns_topic.alerts.arn
      IDLE_CPU_AVG_PCT      = tostring(var.idle_cpu_avg_pct)
      IDLE_CPU_PEAK_PCT     = tostring(var.idle_cpu_peak_pct)
      LOOKBACK_DAYS         = tostring(var.lookback_days)
      SNAPSHOT_MAX_AGE_DAYS = tostring(var.snapshot_max_age_days)
      STOPPED_MIN_DAYS      = tostring(var.stopped_min_days)
      NOTIFY_WHEN_CLEAN     = tostring(var.notify_when_clean)
    })
  }

  depends_on = [aws_cloudwatch_log_group.scanner]
}

resource "aws_lambda_function" "scheduler" {
  function_name    = local.scheduler_name
  description      = "Stops and starts instances tagged ${var.schedule_tag_key}=${var.schedule_tag_value}"
  role             = aws_iam_role.scheduler_lambda.arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "handlers.schedule"
  filename         = data.archive_file.code.output_path
  source_code_hash = data.archive_file.code.output_base64sha256
  timeout          = 120
  memory_size      = 128

  environment {
    variables = merge(local.common_env, {
      DRY_RUN = tostring(var.scheduler_dry_run)
    })
  }

  depends_on = [aws_cloudwatch_log_group.scheduler]
}

# EventBridge Scheduler calls Lambda asynchronously, and async calls retry twice by default.
# For the scanner that means three identical emails when a check fails. No thanks.
resource "aws_lambda_function_event_invoke_config" "scanner" {
  function_name          = aws_lambda_function.scanner.function_name
  maximum_retry_attempts = 0
}

resource "aws_lambda_function_event_invoke_config" "scheduler" {
  function_name          = aws_lambda_function.scheduler.function_name
  maximum_retry_attempts = 1 # a start/stop is safe to repeat
}
