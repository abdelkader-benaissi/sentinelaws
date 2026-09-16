variable "name" { type = string }
variable "environment" { type = string }
variable "vpc_id" { type = string }
variable "public_subnet_ids" { type = list(string) }
variable "app_subnet_ids" { type = list(string) }
variable "app_security_group_id" { type = string }
variable "kms_key_arn" { type = string }
variable "certificate_arn" {
  type        = string
  description = "Validated ACM certificate ARN for the HTTPS listener."
  validation {
    condition     = can(regex("^arn:[^:]+:acm:[^:]+:[0-9]{12}:certificate/", var.certificate_arn))
    error_message = "certificate_arn must be a valid ACM certificate ARN."
  }
}
variable "db_endpoint" { type = string }
variable "db_secret_arn" {
  type      = string
  sensitive = true
}
variable "db_name" {
  type    = string
  default = "sentineldb"
}
variable "instance_type" { type = string }
variable "desired_capacity" { type = number }
variable "min_size" { type = number }
variable "max_size" { type = number }
variable "waf_rate_limit" { type = number }
variable "enable_deletion_protection" { type = bool }
variable "force_destroy_logs" { type = bool }
variable "log_retention_days" {
  type    = number
  default = 30
}
variable "access_log_retention_days" {
  type    = number
  default = 30
}
variable "tags" {
  type    = map(string)
  default = {}
}
