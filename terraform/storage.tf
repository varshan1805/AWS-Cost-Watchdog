# One item per resource per day. Lets the report say "first flagged on 3 Feb",
# which is far more persuasive than "this is idle today".
resource "aws_dynamodb_table" "findings" {
  name         = "${var.project}-findings"
  billing_mode = "PAY_PER_REQUEST" # a few dozen writes a day costs close to nothing
  hash_key     = "resource_id"
  range_key    = "scan_date"

  attribute {
    name = "resource_id"
    type = "S"
  }

  attribute {
    name = "scan_date"
    type = "S"
  }

  # Old rows delete themselves (90 days by default, set in the Lambda)
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  # Point-in-time recovery is off: this is a history log I can rebuild, not
  # data I can't lose, and PITR is billed per GB.
  point_in_time_recovery {
    enabled = false
  }
}
