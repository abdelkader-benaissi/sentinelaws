locals {
  name              = "sentinelaws-dev"
  high_availability = var.deployment_profile == "ha"
  common_tags = {
    Project           = "SentinelAWS"
    Environment       = "dev"
    DeploymentProfile = var.deployment_profile
    ManagedBy         = "Terraform"
    Owner             = var.owner
  }
}

module "detection" {
  source = "../../modules/detection"

  name        = local.name
  alert_email = var.alert_email
  tags        = local.common_tags
}

module "security" {
  source = "../../modules/security"

  name                       = local.name
  alert_topic_arn            = module.detection.alert_topic_arn
  force_destroy_audit_bucket = !local.high_availability
  log_retention_days         = var.log_retention_days
  tags                       = local.common_tags
}

module "networking" {
  source = "../../modules/networking"

  name               = local.name
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
  nat_gateway_per_az = local.high_availability
  kms_key_arn        = module.security.kms_key_arn
  log_retention_days = var.log_retention_days
  tags               = local.common_tags
}

resource "aws_security_group" "application" {
  name_prefix            = "${local.name}-app-"
  description            = "Private application tier with explicit least-privilege rules"
  vpc_id                 = module.networking.vpc_id
  revoke_rules_on_delete = true

  tags = merge(local.common_tags, {
    Name               = "${local.name}-app-sg"
    SentinelAWSManaged = "true"
  })

  lifecycle { create_before_destroy = true }
}

module "database" {
  source = "../../modules/database"

  name                  = local.name
  vpc_id                = module.networking.vpc_id
  subnet_ids            = module.networking.db_subnet_ids
  app_security_group_id = aws_security_group.application.id
  kms_key_arn           = module.security.kms_key_arn
  instance_class        = "db.t4g.micro"
  db_name               = "sentineldb"
  multi_az              = local.high_availability
  deletion_protection   = local.high_availability
  apply_immediately     = !local.high_availability
  log_retention_days    = var.log_retention_days
  tags                  = local.common_tags
}

resource "aws_vpc_security_group_egress_rule" "app_database" {
  security_group_id            = aws_security_group.application.id
  referenced_security_group_id = module.database.security_group_id
  description                  = "PostgreSQL to the database tier"
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_vpc_security_group_egress_rule" "app_https" {
  security_group_id = aws_security_group.application.id
  description       = "HTTPS for package updates and AWS APIs through NAT"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_vpc_security_group_egress_rule" "app_dns_udp" {
  security_group_id = aws_security_group.application.id
  description       = "DNS over UDP to the VPC resolver"
  cidr_ipv4         = module.networking.vpc_cidr
  ip_protocol       = "udp"
  from_port         = 53
  to_port           = 53
}

resource "aws_vpc_security_group_egress_rule" "app_dns_tcp" {
  security_group_id = aws_security_group.application.id
  description       = "DNS over TCP to the VPC resolver"
  cidr_ipv4         = module.networking.vpc_cidr
  ip_protocol       = "tcp"
  from_port         = 53
  to_port           = 53
}

module "application" {
  source = "../../modules/application"

  name                       = local.name
  environment                = "dev"
  vpc_id                     = module.networking.vpc_id
  public_subnet_ids          = module.networking.public_subnet_ids
  app_subnet_ids             = module.networking.app_subnet_ids
  app_security_group_id      = aws_security_group.application.id
  kms_key_arn                = module.security.kms_key_arn
  certificate_arn            = var.certificate_arn
  db_endpoint                = module.database.endpoint
  db_secret_arn              = module.database.secret_arn
  db_name                    = "sentineldb"
  instance_type              = "t3.micro"
  desired_capacity           = local.high_availability ? 2 : 1
  min_size                   = local.high_availability ? 2 : 1
  max_size                   = local.high_availability ? 4 : 2
  waf_rate_limit             = 500
  enable_deletion_protection = local.high_availability
  force_destroy_logs         = !local.high_availability
  log_retention_days         = var.log_retention_days
  access_log_retention_days  = var.log_retention_days
  tags                       = local.common_tags
}

resource "aws_vpc_security_group_ingress_rule" "app_from_alb" {
  security_group_id            = aws_security_group.application.id
  referenced_security_group_id = module.application.alb_security_group_id
  description                  = "Application traffic from the ALB"
  ip_protocol                  = "tcp"
  from_port                    = 8080
  to_port                      = 8080
}

resource "aws_route53_record" "application" {
  count = var.route53_zone_id == null ? 0 : 1

  zone_id = var.route53_zone_id
  name    = var.application_domain
  type    = "A"

  alias {
    name                   = module.application.alb_dns_name
    zone_id                = module.application.alb_zone_id
    evaluate_target_health = true
  }
}

module "remediation" {
  source = "../../modules/remediation"

  name                  = local.name
  vpc_id                = module.networking.vpc_id
  kms_key_arn           = module.security.kms_key_arn
  alert_topic_arn       = module.detection.alert_topic_arn
  waf_ip_set_id         = module.application.waf_ip_set_id
  waf_ip_set_name       = module.application.waf_ip_set_name
  quarantine_source_dir = abspath("${path.root}/../../../lambda/quarantine_instance")
  waf_block_source_dir  = abspath("${path.root}/../../../lambda/waf_ip_block")
  incident_ttl_days     = 90
  log_retention_days    = var.log_retention_days
  tags                  = local.common_tags
}
