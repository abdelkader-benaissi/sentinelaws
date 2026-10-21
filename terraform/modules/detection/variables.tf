variable "name" { type = string }
variable "kms_key_arn" {
  type        = string
  description = "Customer-managed key for the alert topic."
}
variable "cloudtrail_log_group_name" {
  type        = string
  description = "CloudWatch Logs group that receives the CloudTrail trail."
}
variable "alert_email" {
  type      = string
  default   = null
  nullable  = true
  sensitive = true
}
variable "tags" {
  type    = map(string)
  default = {}
}
