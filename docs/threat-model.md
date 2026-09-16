# Threat model

## Assets

- Application and database data
- RDS credentials stored in Secrets Manager
- KMS keys and encrypted audit records
- EC2 instance roles and temporary credentials
- Terraform state and deployment credentials
- Detection findings and incident-response records

## Trust boundaries

| Boundary | Allowed path | Primary controls |
|---|---|---|
| Internet to edge | HTTPS/443; TCP/80 redirects only | ACM TLS policy, WAF, Shield Standard, ALB security group |
| ALB to application | TCP/8080 | Source-security-group rule only |
| Application to database | TLS over TCP/5432 | Source-SG rule, private DNS, RDS `force_ssl`, managed secret |
| Application to AWS APIs | HTTPS egress | IAM role, NAT, CloudTrail |
| Detection to remediation | EventBridge invocation | Resource policy, idempotency, encrypted DLQ, bounded concurrency |
| Operators to instances | SSM control/data channels | IAM, Session Manager, CloudTrail; no SSH |

## Priority abuse cases

| Threat | Prevent | Detect | Respond |
|---|---|---|---|
| Internet exploitation | WAF managed rules, patched AMI, private compute | WAF logs, application logs, GuardDuty | Block source, replace instance |
| Stolen instance credentials | Scoped IAM role, IMDSv2 | GuardDuty, CloudTrail | Quarantine tagged instance and investigate |
| Public storage exposure | S3 Block Public Access, bucket policy | AWS Config and Security Hub | Controlled Config remediation in Phase 2 |
| Database exposure | Isolated subnet, no public endpoint, SG reference | Config and VPC Flow Logs | Revoke path, rotate RDS secret |
| Log deletion or tampering | Dedicated encrypted bucket, versioning, key separation | CloudTrail validation | Preserve evidence and investigate principal |
| Terraform credential leakage | OIDC in CI, ignored local state and tfvars | Secret scanning | Revoke session/role and rotate affected secret |

## Automation safety invariants

1. EC2 quarantine requires `SentinelAWSManaged=true`.
2. Quarantine never terminates an instance or detaches storage.
3. IP blocking rejects non-public addresses.
4. Every action writes an expiring ledger entry; duplicate IDs do not mutate resources twice.
5. Quarantine replaces security groups on every attached network interface.
6. Automation roles cannot change IAM users, roles, policies, KMS keys, or logs.
