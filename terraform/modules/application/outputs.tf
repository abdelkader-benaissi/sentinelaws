output "alb_dns_name" { value = aws_lb.this.dns_name }
output "alb_zone_id" { value = aws_lb.this.zone_id }
output "alb_security_group_id" { value = aws_security_group.alb.id }
output "waf_ip_set_id" { value = aws_wafv2_ip_set.incident_blocklist.id }
output "waf_ip_set_name" { value = aws_wafv2_ip_set.incident_blocklist.name }
output "waf_web_acl_arn" { value = aws_wafv2_web_acl.this.arn }
