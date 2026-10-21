data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_region" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition
  region     = data.aws_region.current.region

  # CloudTrail detections, after the CIS AWS Foundations Benchmark monitoring
  # controls (Security Hub CloudWatch.1-14). Each pattern becomes a CloudWatch
  # Logs metric filter on the trail's log group and an alarm on the alert topic.
  cloudtrail_alarms = {
    root-account-usage = {
      description = "The root user signed in or called an API."
      pattern     = "{ $.userIdentity.type = \"Root\" && $.userIdentity.invokedBy NOT EXISTS && $.eventType != \"AwsServiceEvent\" }"
    }
    console-signin-without-mfa = {
      description = "An IAM user signed in to the console without MFA."
      pattern     = "{ ($.eventName = \"ConsoleLogin\") && ($.additionalEventData.MFAUsed != \"Yes\") && ($.userIdentity.type = \"IAMUser\") && ($.responseElements.ConsoleLogin = \"Success\") }"
    }
    iam-policy-changes = {
      description = "An IAM policy was created, changed, attached, or detached."
      pattern     = "{ ($.eventName = DeleteGroupPolicy) || ($.eventName = DeleteRolePolicy) || ($.eventName = DeleteUserPolicy) || ($.eventName = PutGroupPolicy) || ($.eventName = PutRolePolicy) || ($.eventName = PutUserPolicy) || ($.eventName = CreatePolicy) || ($.eventName = DeletePolicy) || ($.eventName = CreatePolicyVersion) || ($.eventName = DeletePolicyVersion) || ($.eventName = AttachRolePolicy) || ($.eventName = DetachRolePolicy) || ($.eventName = AttachUserPolicy) || ($.eventName = DetachUserPolicy) || ($.eventName = AttachGroupPolicy) || ($.eventName = DetachGroupPolicy) }"
    }
    cloudtrail-changes = {
      description = "A CloudTrail trail was created, changed, stopped, or deleted."
      pattern     = "{ ($.eventName = CreateTrail) || ($.eventName = UpdateTrail) || ($.eventName = DeleteTrail) || ($.eventName = StartLogging) || ($.eventName = StopLogging) }"
    }
    config-changes = {
      description = "The AWS Config recorder or delivery channel was changed or stopped."
      pattern     = "{ ($.eventSource = config.amazonaws.com) && (($.eventName = StopConfigurationRecorder) || ($.eventName = DeleteDeliveryChannel) || ($.eventName = PutDeliveryChannel) || ($.eventName = PutConfigurationRecorder)) }"
    }
    kms-key-disabled-or-deleted = {
      description = "A KMS key was disabled or scheduled for deletion."
      pattern     = "{ ($.eventSource = kms.amazonaws.com) && (($.eventName = DisableKey) || ($.eventName = ScheduleKeyDeletion)) }"
    }
    security-group-changes = {
      description = "A security group or one of its rules was created, changed, or deleted."
      pattern     = "{ ($.eventName = AuthorizeSecurityGroupIngress) || ($.eventName = AuthorizeSecurityGroupEgress) || ($.eventName = RevokeSecurityGroupIngress) || ($.eventName = RevokeSecurityGroupEgress) || ($.eventName = CreateSecurityGroup) || ($.eventName = DeleteSecurityGroup) }"
    }
  }
}

resource "aws_guardduty_detector" "this" {
  enable                       = true
  finding_publishing_frequency = "FIFTEEN_MINUTES"
  tags                         = var.tags
}

resource "aws_guardduty_detector_feature" "s3" {
  detector_id = aws_guardduty_detector.this.id
  name        = "S3_DATA_EVENTS"
  status      = "ENABLED"
}

resource "aws_guardduty_detector_feature" "malware" {
  detector_id = aws_guardduty_detector.this.id
  name        = "EBS_MALWARE_PROTECTION"
  status      = "ENABLED"
}

resource "aws_securityhub_account" "this" {
  enable_default_standards  = true
  control_finding_generator = "SECURITY_CONTROL"
  auto_enable_controls      = true
}

# The alert topic uses the project's customer-managed key: CloudWatch alarms and
# EventBridge rules cannot publish to a topic encrypted with the AWS managed
# aws/sns key.
resource "aws_sns_topic" "alerts" {
  name              = "${var.name}-security-alerts"
  kms_master_key_id = var.kms_key_arn
  tags              = var.tags
}

data "aws_iam_policy_document" "alerts" {
  statement {
    sid       = "ConfigComplianceRule"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.alerts.arn]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_cloudwatch_event_rule.config_noncompliant.arn]
    }
  }

  statement {
    sid       = "CloudTrailAlarms"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.alerts.arn]
    principals {
      type        = "Service"
      identifiers = ["cloudwatch.amazonaws.com"]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:${local.partition}:cloudwatch:${local.region}:${local.account_id}:alarm:${var.name}-*"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_sns_topic_policy" "alerts" {
  arn    = aws_sns_topic.alerts.arn
  policy = data.aws_iam_policy_document.alerts.json
}

resource "aws_sns_topic_subscription" "email" {
  count = var.alert_email == null ? 0 : 1

  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# CloudTrail -> CloudWatch Logs -> metric filter -> alarm -> SNS.
resource "aws_cloudwatch_log_metric_filter" "cloudtrail" {
  for_each = local.cloudtrail_alarms

  name           = "${var.name}-${each.key}"
  log_group_name = var.cloudtrail_log_group_name
  pattern        = each.value.pattern

  metric_transformation {
    name      = each.key
    namespace = "SentinelAWS/CloudTrail"
    value     = "1"
  }
}

resource "aws_cloudwatch_metric_alarm" "cloudtrail" {
  for_each = local.cloudtrail_alarms

  alarm_name          = "${var.name}-${each.key}"
  alarm_description   = each.value.description
  namespace           = "SentinelAWS/CloudTrail"
  metric_name         = aws_cloudwatch_log_metric_filter.cloudtrail[each.key].metric_transformation[0].name
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  tags                = var.tags
}

# AWS Config -> EventBridge -> SNS. Config publishes every compliance change to
# the default event bus; only transitions to NON_COMPLIANT raise an alert.
resource "aws_cloudwatch_event_rule" "config_noncompliant" {
  name        = "${var.name}-config-noncompliant"
  description = "Alert when an AWS Config rule marks a resource NON_COMPLIANT"

  event_pattern = jsonencode({
    source        = ["aws.config"]
    "detail-type" = ["Config Rules Compliance Change"]
    detail = {
      messageType = ["ComplianceChangeNotification"]
      newEvaluationResult = {
        complianceType = ["NON_COMPLIANT"]
      }
    }
  })

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "config_noncompliant" {
  rule      = aws_cloudwatch_event_rule.config_noncompliant.name
  target_id = "security-alert-topic"
  arn       = aws_sns_topic.alerts.arn

  input_transformer {
    input_paths = {
      rule     = "$.detail.configRuleName"
      type     = "$.detail.resourceType"
      resource = "$.detail.resourceId"
      region   = "$.region"
    }
    input_template = "\"AWS Config: <type> <resource> in <region> is NON_COMPLIANT with rule <rule>.\""
  }

  depends_on = [aws_sns_topic_policy.alerts]
}
