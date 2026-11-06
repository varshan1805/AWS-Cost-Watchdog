# Not encrypted with the AWS-managed aws/sns key on purpose: CloudWatch alarms
# can't publish to a topic using that key. A customer-managed KMS key would
# work but costs $1/month, which is more than everything else here combined.
resource "aws_sns_topic" "alerts" {
  name = "${var.project}-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# A watchdog that dies silently is worse than none, so both functions alarm on errors
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each = {
    scanner   = aws_lambda_function.scanner.function_name
    scheduler = aws_lambda_function.scheduler.function_name
  }

  alarm_name          = "${each.value}-errors"
  alarm_description   = "${each.value} failed. Check its CloudWatch logs."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = each.value }
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# Safety net for the whole account, including mistakes the watchdog can't see
resource "aws_budgets_budget" "monthly" {
  name         = "${var.project}-monthly-budget"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.alert_email]
  }
}
