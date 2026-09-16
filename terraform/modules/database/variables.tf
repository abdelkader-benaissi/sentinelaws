variable "name" { type = string }
variable "vpc_id" { type = string }
variable "subnet_ids" { type = list(string) }
variable "app_security_group_id" { type = string }
variable "kms_key_arn" { type = string }
variable "instance_class" { type = string }
variable "db_name" {
  type    = string
  default = "sentineldb"
}
variable "multi_az" { type = bool }
variable "deletion_protection" { type = bool }
variable "apply_immediately" {
  type    = bool
  default = false
}
variable "log_retention_days" {
  type    = number
  default = 30
}
variable "tags" {
  type    = map(string)
  default = {}
}
