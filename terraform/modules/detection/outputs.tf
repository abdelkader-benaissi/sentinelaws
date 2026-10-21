output "guardduty_detector_id" { value = aws_guardduty_detector.this.id }
output "securityhub_arn" { value = aws_securityhub_account.this.arn }
output "alert_topic_arn" { value = aws_sns_topic.alerts.arn }
output "cloudtrail_alarm_names" {
  value = [for alarm in aws_cloudwatch_metric_alarm.cloudtrail : alarm.alarm_name]
}
