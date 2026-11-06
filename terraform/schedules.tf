resource "aws_scheduler_schedule_group" "this" {
  name = var.project
}

resource "aws_scheduler_schedule" "daily_scan" {
  name                         = "${var.project}-daily-scan"
  group_name                   = aws_scheduler_schedule_group.this.name
  schedule_expression          = var.scan_cron
  schedule_expression_timezone = var.timezone

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.scanner.arn
    role_arn = aws_iam_role.eventbridge.arn
    input    = jsonencode({ source = "daily-schedule" })

    retry_policy {
      maximum_retry_attempts = 0
    }
  }
}

resource "aws_scheduler_schedule" "stop_tagged" {
  name                         = "${var.project}-stop-tagged"
  group_name                   = aws_scheduler_schedule_group.this.name
  schedule_expression          = var.stop_cron
  schedule_expression_timezone = var.timezone

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.scheduler.arn
    role_arn = aws_iam_role.eventbridge.arn
    input    = jsonencode({ action = "stop" })
  }
}

resource "aws_scheduler_schedule" "start_tagged" {
  name                         = "${var.project}-start-tagged"
  group_name                   = aws_scheduler_schedule_group.this.name
  schedule_expression          = var.start_cron
  schedule_expression_timezone = var.timezone

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.scheduler.arn
    role_arn = aws_iam_role.eventbridge.arn
    input    = jsonencode({ action = "start" })
  }
}
