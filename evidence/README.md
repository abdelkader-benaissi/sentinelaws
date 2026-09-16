# Deployment evidence checklist

Do not commit credentials, account IDs, secret values, public client addresses,
or unredacted console screenshots.

- [ ] Reviewed Terraform plan and cost estimate
- [ ] HTTPS redirect and TLS policy
- [ ] `/health` response and `/ready` RDS connection
- [ ] Two healthy targets across AZs in the `ha` profile
- [ ] No public IP and no inbound SSH on application instances
- [ ] RDS private, encrypted, TLS forced, and Multi-AZ in the `ha` profile
- [ ] GuardDuty sample finding reaches EventBridge
- [ ] Tagged instance: every ENI quarantined; original groups recorded
- [ ] Untagged instance: automation refuses containment
- [ ] WAF public IP insertion, duplicate replay, and private-IP refusal
- [ ] CloudTrail S3/CloudWatch delivery, WAF logs, ALB logs, and VPC Flow Logs
- [ ] Security Hub and AWS Config results
- [ ] Reviewed destroy plan and post-destroy resource check
