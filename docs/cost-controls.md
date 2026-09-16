# Cost controls

## Recurring-cost resources

- NAT Gateway and processed bytes
- Application Load Balancer and LCUs
- RDS instance, storage, backups, and Multi-AZ standby
- AWS Config evaluations and configuration items
- GuardDuty and Security Hub analysis volume
- CloudWatch Logs ingestion and retention
- CloudTrail events outside the free management-event allowance

## Lab defaults

- One NAT Gateway rather than one per Availability Zone
- One `t3.micro` application instance
- `db.t4g.micro` RDS instance with Multi-AZ disabled
- Seven-day CloudWatch log retention
- Thirty-day noncurrent S3 version expiration
- No Route 53 domain, ACM certificate, CloudFront, or paid Shield tier

These choices trade availability for cost in the development environment. The
production design uses one NAT Gateway per Availability Zone and Multi-AZ RDS.

## Mandatory controls

1. Create an AWS Budget before deployment.
2. Tag all resources with `Project=SentinelAWS` and an owner identifier.
3. Apply only from a reviewed saved plan.
4. Run the lab for a defined evidence window.
5. Destroy the environment and verify that no NAT Gateway, ALB, RDS instance,
   Elastic IP, log group, or snapshot remains unintentionally.

