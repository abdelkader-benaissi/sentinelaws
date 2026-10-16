# Vendored AWS Architecture Icons

These PNG files are the official AWS Architecture Icons, redistributed here so
the diagram renders reproducibly without a network fetch or a third-party
package.

| File | AWS icon |
|---|---|
| `acm.png` | Certificate Manager |
| `alb.png` | Elastic Load Balancing - Application Load Balancer |
| `cloudtrail.png` | CloudTrail |
| `cloudwatch.png` | CloudWatch Logs |
| `config.png` | AWS Config |
| `dynamodb.png` | DynamoDB |
| `ec2.png` | EC2 instance |
| `eventbridge.png` | EventBridge |
| `flowlogs.png` | VPC Flow Logs |
| `guardduty.png` | GuardDuty |
| `igw.png` | Internet Gateway |
| `ipset.png` | WAF filtering rule |
| `lambda.png` | Lambda |
| `nat.png` | NAT Gateway |
| `rds.png` | RDS PostgreSQL instance |
| `route53.png` | Route 53 |
| `s3.png` | Simple Storage Service (S3) bucket |
| `sechub.png` | Security Hub |
| `sns.png` | Simple Notification Service (SNS) |
| `sqs.png` | Simple Queue Service (SQS) |
| `waf.png` | AWS WAF |

Source: the icon set published by AWS at
<https://aws.amazon.com/architecture/icons/>, as redistributed by the
`diagrams` Python package (`resources/aws/`).

The icons remain the property of Amazon Web Services and are used under the
AWS Architecture Icons terms of use, which permit their use in architecture
diagrams that describe AWS services. They are not covered by this repository's
MIT licence.

`render.py` resolves this directory relative to its own location
(`architecture/icons/`), so the diagram does not depend on any installed
package or machine-specific path.