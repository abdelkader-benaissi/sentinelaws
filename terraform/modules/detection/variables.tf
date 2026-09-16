variable "name" { type = string }
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

