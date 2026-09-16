output "application_url" {
  description = "HTTP lab endpoint. Add ACM and HTTPS before any non-lab use."
  value       = "http://${module.application.alb_dns_name}"
}

output "rds_endpoint" {
  value = module.database.endpoint
}

output "rds_master_secret_arn" {
  value     = module.database.secret_arn
  sensitive = true
}

output "audit_bucket" {
  value = module.security.audit_bucket_name
}

output "incident_table" {
  value = module.remediation.incident_table_name
}

output "response_functions" {
  value = {
    quarantine = module.remediation.quarantine_function_name
    waf_block  = module.remediation.waf_block_function_name
  }
}

