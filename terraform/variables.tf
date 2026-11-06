variable "project" {
  description = "Prefix for every resource name. The deploy role's permissions are scoped to this prefix."
  type        = string
  default     = "cost-watchdog"
}

variable "aws_region" {
  description = "Where the watchdog itself runs."
  type        = string
  default     = "ap-south-1"
}

variable "scan_regions" {
  description = "Regions to scan for waste."
  type        = list(string)
  default     = ["ap-south-1"]
}

variable "alert_email" {
  description = "Gets the daily report, Lambda failure alarms and budget alerts. You'll need to confirm the subscription email from AWS."
  type        = string
}

variable "monthly_budget_usd" {
  description = "AWS Budgets alert threshold for the whole account."
  type        = number
  default     = 10
}

variable "timezone" {
  description = "Time zone for all schedules below."
  type        = string
  default     = "Asia/Kolkata"
}

variable "scan_cron" {
  description = "When the daily scan runs (EventBridge Scheduler cron, in var.timezone)."
  type        = string
  default     = "cron(0 8 * * ? *)" # 08:00 every day
}

variable "stop_cron" {
  description = "When tagged instances are stopped."
  type        = string
  default     = "cron(0 20 ? * MON-FRI *)" # 20:00 weekdays
}

variable "start_cron" {
  description = "When tagged instances are started again."
  type        = string
  default     = "cron(0 9 ? * MON-FRI *)" # 09:00 weekdays
}

variable "schedule_tag_key" {
  type    = string
  default = "Schedule"
}

variable "schedule_tag_value" {
  type    = string
  default = "office-hours"
}

variable "scheduler_dry_run" {
  description = "When true, the start/stop Lambda only logs what it would do. Start with true, check the logs, then switch off."
  type        = bool
  default     = true
}

variable "idle_cpu_avg_pct" {
  type    = number
  default = 5
}

variable "idle_cpu_peak_pct" {
  type    = number
  default = 30
}

variable "lookback_days" {
  type    = number
  default = 7
}

variable "snapshot_max_age_days" {
  type    = number
  default = 90
}

variable "stopped_min_days" {
  type    = number
  default = 14
}

variable "notify_when_clean" {
  description = "Send an email even when nothing is found (a daily 'still alive' message)."
  type        = bool
  default     = false
}

variable "log_retention_days" {
  type    = number
  default = 14
}
