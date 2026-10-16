variable "aws_region" {
  description = "AWS Region for the development environment."
  type        = string
  default     = "us-east-1"
}

variable "availability_zones" {
  description = "Exactly two Availability Zones in aws_region."
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]

  validation {
    condition     = length(var.availability_zones) == 2
    error_message = "Provide exactly two Availability Zones."
  }
}

variable "vpc_cidr" {
  description = "CIDR assigned to the SentinelAWS VPC."
  type        = string
  default     = "10.20.0.0/16"
}

variable "owner" {
  description = "Owner tag for attribution and cost reporting."
  type        = string
}

variable "alert_email" {
  description = "Optional address for SNS security alerts. Confirmation is required."
  type        = string
  default     = null
  nullable    = true
  sensitive   = true
}

variable "deployment_profile" {
  description = "ha matches the architecture diagram (two instances, one NAT Gateway per AZ, Multi-AZ RDS, deletion protection); lab is a cheaper disposable single-AZ variant."
  type        = string
  default     = "ha"

  validation {
    condition     = contains(["lab", "ha"], var.deployment_profile)
    error_message = "deployment_profile must be either lab or ha."
  }
}

variable "certificate_arn" {
  description = "Validated ACM certificate ARN for application_domain."
  type        = string
}

variable "application_domain" {
  description = "DNS name covered by certificate_arn."
  type        = string
}

variable "route53_zone_id" {
  description = "Optional Route 53 hosted zone ID. Leave null when DNS is managed elsewhere."
  type        = string
  default     = null
  nullable    = true
}

variable "log_retention_days" {
  description = "CloudWatch and access-log retention for the lab."
  type        = number
  default     = 30
}
