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

variable "database_multi_az" {
  description = "Enable Multi-AZ RDS. False is cheaper for a short-lived lab."
  type        = bool
  default     = false
}

variable "database_deletion_protection" {
  description = "Protect RDS from deletion. Keep false for a disposable lab."
  type        = bool
  default     = false
}

