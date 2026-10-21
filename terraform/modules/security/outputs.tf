output "kms_key_arn" { value = aws_kms_key.this.arn }
output "audit_bucket_name" { value = aws_s3_bucket.audit.id }
output "cloudtrail_arn" { value = aws_cloudtrail.this.arn }
output "cloudtrail_log_group_name" { value = aws_cloudwatch_log_group.cloudtrail.name }
