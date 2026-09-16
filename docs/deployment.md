# Deployment guide

## Prerequisites

- Dedicated AWS sandbox account
- Terraform 1.10 or later
- AWS CLI v2 with short-lived credentials
- Permissions to create VPC, EC2, ELB, Auto Scaling, RDS, KMS, S3,
  CloudTrail, Config, GuardDuty, Security Hub, Lambda, EventBridge, DynamoDB,
  SNS, WAF, IAM roles, and service-linked roles
- An AWS Budget created before deployment
- A validated ACM certificate in the deployment Region
- A DNS name covered by the certificate; optionally, a Route 53 hosted zone

Do not use long-lived IAM user keys in GitHub Actions. A later phase will add
GitHub OIDC with a narrowly scoped deployment role.

## Preflight

```bash
aws sts get-caller-identity
aws configure get region
cd terraform/environments/dev
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform fmt -check -recursive
terraform validate
terraform plan -out=tfplan
terraform show tfplan
```

Review the target account, Region, Availability Zones, IAM policies, security
group rules, RDS settings, and all recurring-cost resources before applying.

## Apply

```bash
terraform apply tfplan
terraform output
curl "$(terraform output -raw application_url)/health"
curl "$(terraform output -raw application_url)/ready"
```

Expected response:

```json
{"status": "healthy"}
```

`/ready` must return `status=ready` and `database.status=connected`. This proves
the private application tier retrieved the managed RDS secret and completed a
TLS-protected PostgreSQL query.

## Verification

```bash
aws ec2 describe-instances \
  --filters 'Name=tag:Project,Values=SentinelAWS' \
  --query 'Reservations[].Instances[].{Id:InstanceId,PublicIp:PublicIpAddress,Subnet:SubnetId}'

aws rds describe-db-instances \
  --query 'DBInstances[?contains(DBInstanceIdentifier, `sentinelaws`)].{Public:PubliclyAccessible,Encrypted:StorageEncrypted,MultiAZ:MultiAZ}'

aws cloudtrail get-trail-status --name sentinelaws-dev
aws guardduty list-detectors
aws securityhub describe-hub
```

The EC2 instances must have no public IP, RDS must report `Public=false` and
`Encrypted=true`, and no security group should allow inbound TCP/22. For final
availability evidence, change `deployment_profile` to `ha`, review the cost
increase in the saved plan, and verify two healthy targets across both AZs.

## Teardown

Export required screenshots and incident evidence first. Then:

```bash
terraform plan -destroy -out=destroy.tfplan
terraform show destroy.tfplan
terraform apply destroy.tfplan
```

Verify manually that no project NAT Gateway, Elastic IP, ALB, RDS instance,
snapshot, or log group remains. The development configuration intentionally
allows destruction; it is not a production retention design.
