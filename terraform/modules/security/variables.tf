variable "name" { type = string }
variable "alert_topic_arn" { type = string }
variable "force_destroy_audit_bucket" {
  type        = bool
  description = "Allow deletion of a non-empty audit bucket only for disposable lab deployments."
}
variable "log_retention_days" {
  type    = number
  default = 30
}
variable "tags" {
  type    = map(string)
  default = {}
}
