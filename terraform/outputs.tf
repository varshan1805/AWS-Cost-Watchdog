output "scanner_function" {
  value = aws_lambda_function.scanner.function_name
}

output "scheduler_function" {
  value = aws_lambda_function.scheduler.function_name
}

output "findings_table" {
  value = aws_dynamodb_table.findings.name
}

output "alerts_topic_arn" {
  value = aws_sns_topic.alerts.arn
}

output "run_a_scan_now" {
  description = "Paste this to trigger a scan without waiting for 08:00"
  value       = "aws lambda invoke --function-name ${aws_lambda_function.scanner.function_name} --region ${var.aws_region} out.json && cat out.json"
}
