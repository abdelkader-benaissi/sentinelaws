data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_region" "current" {}

resource "aws_security_group" "quarantine" {
  name_prefix = "${var.name}-quarantine-"
  description = "Containment group with no ingress or egress"
  vpc_id      = var.vpc_id

  tags = merge(var.tags, {
    Name               = "${var.name}-quarantine-sg"
    SentinelAWSManaged = "true"
  })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_dynamodb_table" "incidents" {
  name         = "${var.name}-incident-ledger"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "finding_id"

  attribute {
    name = "finding_id"
    type = "S"
  }

  point_in_time_recovery { enabled = true }
  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_arn
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  tags = merge(var.tags, { DataClassification = "security-finding" })
}

data "archive_file" "quarantine" {
  type        = "zip"
  source_dir  = var.quarantine_source_dir
  output_path = "${path.root}/.terraform/${var.name}-quarantine.zip"
}

data "archive_file" "waf_block" {
  type        = "zip"
  source_dir  = var.waf_block_source_dir
  output_path = "${path.root}/.terraform/${var.name}-waf-block.zip"
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "quarantine" {
  name               = "${var.name}-quarantine"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = var.tags
}

resource "aws_iam_role" "waf_block" {
  name               = "${var.name}-waf-block"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "quarantine_logs" {
  role       = aws_iam_role.quarantine.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "waf_logs" {
  role       = aws_iam_role.waf_block.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "quarantine_xray" {
  role       = aws_iam_role.quarantine.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AWSXRayDaemonWriteAccess"
}

resource "aws_iam_role_policy_attachment" "waf_xray" {
  role       = aws_iam_role.waf_block.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AWSXRayDaemonWriteAccess"
}

resource "aws_sqs_queue" "quarantine_dlq" {
  name                      = "${var.name}-quarantine-dlq"
  message_retention_seconds = 1209600
  kms_master_key_id         = var.kms_key_arn
  tags                      = var.tags
}

resource "aws_sqs_queue" "waf_block_dlq" {
  name                      = "${var.name}-waf-block-dlq"
  message_retention_seconds = 1209600
  kms_master_key_id         = var.kms_key_arn
  tags                      = var.tags
}

data "aws_iam_policy_document" "quarantine" {
  statement {
    sid       = "DescribeTarget"
    actions   = ["ec2:DescribeInstances"]
    resources = ["*"]
  }

  statement {
    sid       = "QuarantineNetworkInterfaces"
    actions   = ["ec2:ModifyNetworkInterfaceAttribute"]
    resources = ["arn:${data.aws_partition.current.partition}:ec2:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:network-interface/*"]
  }

  statement {
    sid       = "WriteIncidentLedger"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem"]
    resources = [aws_dynamodb_table.incidents.arn]
  }

  statement {
    sid       = "PublishAlert"
    actions   = ["sns:Publish"]
    resources = [var.alert_topic_arn]
  }

  statement {
    sid       = "SendFailureToDLQ"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.quarantine_dlq.arn]
  }

  statement {
    sid       = "DecryptConfiguration"
    actions   = ["kms:Decrypt"]
    resources = [var.kms_key_arn]
  }
}

resource "aws_iam_role_policy" "quarantine" {
  name   = "contain-managed-instance"
  role   = aws_iam_role.quarantine.id
  policy = data.aws_iam_policy_document.quarantine.json
}

data "aws_iam_policy_document" "waf_block" {
  statement {
    sid = "UpdateOnlyIncidentIPSet"
    actions = [
      "wafv2:GetIPSet",
      "wafv2:UpdateIPSet"
    ]
    resources = [
      "arn:${data.aws_partition.current.partition}:wafv2:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:regional/ipset/${var.waf_ip_set_name}/${var.waf_ip_set_id}"
    ]
  }

  statement {
    sid       = "WriteIncidentLedger"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem"]
    resources = [aws_dynamodb_table.incidents.arn]
  }

  statement {
    sid       = "PublishAlert"
    actions   = ["sns:Publish"]
    resources = [var.alert_topic_arn]
  }

  statement {
    sid       = "SendFailureToDLQ"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.waf_block_dlq.arn]
  }

  statement {
    sid       = "DecryptConfiguration"
    actions   = ["kms:Decrypt"]
    resources = [var.kms_key_arn]
  }
}

resource "aws_iam_role_policy" "waf_block" {
  name   = "update-incident-ip-set"
  role   = aws_iam_role.waf_block.id
  policy = data.aws_iam_policy_document.waf_block.json
}

#checkov:skip=CKV_AWS_117:The function calls regional AWS APIs only and does not need VPC access.
#checkov:skip=CKV_AWS_272:Code signing is documented as a production control and omitted from this educational lab.
resource "aws_lambda_function" "quarantine" {
  function_name    = "${var.name}-quarantine-instance"
  role             = aws_iam_role.quarantine.arn
  runtime          = "python3.13"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.quarantine.output_path
  source_code_hash = data.archive_file.quarantine.output_base64sha256
  timeout          = 30
  memory_size      = 128
  kms_key_arn      = var.kms_key_arn
  reserved_concurrent_executions = 5

  tracing_config { mode = "Active" }
  dead_letter_config { target_arn = aws_sqs_queue.quarantine_dlq.arn }

  environment {
    variables = {
      QUARANTINE_SECURITY_GROUP_ID = aws_security_group.quarantine.id
      INCIDENT_TABLE_NAME          = aws_dynamodb_table.incidents.name
      ALERT_TOPIC_ARN              = var.alert_topic_arn
      INCIDENT_TTL_DAYS            = tostring(var.incident_ttl_days)
    }
  }

  tags = var.tags
}

#checkov:skip=CKV_AWS_117:The function calls regional AWS APIs only and does not need VPC access.
#checkov:skip=CKV_AWS_272:Code signing is documented as a production control and omitted from this educational lab.
resource "aws_lambda_function" "waf_block" {
  function_name    = "${var.name}-waf-ip-block"
  role             = aws_iam_role.waf_block.arn
  runtime          = "python3.13"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.waf_block.output_path
  source_code_hash = data.archive_file.waf_block.output_base64sha256
  timeout          = 30
  memory_size      = 128
  kms_key_arn      = var.kms_key_arn
  reserved_concurrent_executions = 5

  tracing_config { mode = "Active" }
  dead_letter_config { target_arn = aws_sqs_queue.waf_block_dlq.arn }

  environment {
    variables = {
      WAF_IP_SET_ID       = var.waf_ip_set_id
      WAF_IP_SET_NAME     = var.waf_ip_set_name
      INCIDENT_TABLE_NAME = aws_dynamodb_table.incidents.name
      ALERT_TOPIC_ARN     = var.alert_topic_arn
      INCIDENT_TTL_DAYS   = tostring(var.incident_ttl_days)
    }
  }

  tags = var.tags
}

resource "aws_cloudwatch_event_rule" "high_severity_guardduty" {
  name        = "${var.name}-high-severity-guardduty"
  description = "Route high-severity GuardDuty findings to controlled response functions"

  event_pattern = jsonencode({
    source        = ["aws.guardduty"]
    "detail-type" = ["GuardDuty Finding"]
    detail = {
      severity = [{ numeric = [">=", 7] }]
    }
  })

  tags = var.tags
}

data "aws_iam_policy_document" "quarantine_dlq" {
  statement {
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.quarantine_dlq.arn]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_cloudwatch_event_rule.high_severity_guardduty.arn]
    }
  }
}

resource "aws_sqs_queue_policy" "quarantine_dlq" {
  queue_url = aws_sqs_queue.quarantine_dlq.id
  policy    = data.aws_iam_policy_document.quarantine_dlq.json
}

data "aws_iam_policy_document" "waf_block_dlq" {
  statement {
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.waf_block_dlq.arn]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_cloudwatch_event_rule.high_severity_guardduty.arn]
    }
  }
}

resource "aws_sqs_queue_policy" "waf_block_dlq" {
  queue_url = aws_sqs_queue.waf_block_dlq.id
  policy    = data.aws_iam_policy_document.waf_block_dlq.json
}

resource "aws_cloudwatch_event_target" "quarantine" {
  rule      = aws_cloudwatch_event_rule.high_severity_guardduty.name
  target_id = "quarantine-instance"
  arn       = aws_lambda_function.quarantine.arn

  dead_letter_config { arn = aws_sqs_queue.quarantine_dlq.arn }
  retry_policy {
    maximum_event_age_in_seconds = 3600
    maximum_retry_attempts       = 2
  }
}

resource "aws_cloudwatch_event_target" "waf_block" {
  rule      = aws_cloudwatch_event_rule.high_severity_guardduty.name
  target_id = "block-remote-ip"
  arn       = aws_lambda_function.waf_block.arn

  dead_letter_config { arn = aws_sqs_queue.waf_block_dlq.arn }
  retry_policy {
    maximum_event_age_in_seconds = 3600
    maximum_retry_attempts       = 2
  }
}

resource "aws_lambda_permission" "eventbridge_quarantine" {
  statement_id  = "AllowEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.quarantine.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.high_severity_guardduty.arn
}

resource "aws_lambda_permission" "eventbridge_waf" {
  statement_id  = "AllowEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.waf_block.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.high_severity_guardduty.arn
}

resource "aws_cloudwatch_log_group" "quarantine" {
  name              = "/aws/lambda/${aws_lambda_function.quarantine.function_name}"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.kms_key_arn
  tags              = var.tags
}

resource "aws_cloudwatch_log_group" "waf_block" {
  name              = "/aws/lambda/${aws_lambda_function.waf_block.function_name}"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.kms_key_arn
  tags              = var.tags
}
