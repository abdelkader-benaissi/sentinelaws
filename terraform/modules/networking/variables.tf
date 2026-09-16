variable "name" { type = string }
variable "vpc_cidr" {
  type    = string
  default = "10.20.0.0/16"
}
variable "availability_zones" {
  type = list(string)
  validation {
    condition     = length(var.availability_zones) == 2
    error_message = "Exactly two Availability Zones are required."
  }
}
variable "nat_gateway_per_az" {
  type        = bool
  description = "Create one NAT Gateway per AZ for HA; false uses one lower-cost NAT Gateway."
}
variable "kms_key_arn" { type = string }
variable "log_retention_days" {
  type    = number
  default = 30
}
variable "tags" {
  type    = map(string)
  default = {}
}
