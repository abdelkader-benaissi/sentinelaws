variable "name" { type = string }
variable "vpc_id" { type = string }
variable "kms_key_arn" { type = string }
variable "alert_topic_arn" { type = string }
variable "waf_ip_set_id" { type = string }
variable "waf_ip_set_name" { type = string }
variable "quarantine_source_dir" { type = string }
variable "waf_block_source_dir" { type = string }
variable "incident_ttl_days" {
  type    = number
  default = 90
}
variable "log_retention_days" {
  type    = number
  default = 30
}
variable "tags" {
  type    = map(string)
  default = {}
}
