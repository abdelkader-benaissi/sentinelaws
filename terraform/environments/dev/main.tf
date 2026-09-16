locals {
  name = "sentinelaws-dev"
  common_tags = {
    Project     = "SentinelAWS"
    Environment = "dev"
    ManagedBy   = "Terraform"
    Owner       = var.owner
  }
}

module "security" {
  source = "../../modules/security"

  name = local.name
  tags = local.common_tags
}

module "networking" {
  source = "../../modules/networking"

  name               = local.name
  vpc_cidr           = "10.20.0.0/16"
  availability_zones = var.availability_zones
  tags               = local.common_tags
}

module "application" {
  source = "../../modules/application"

  name              = local.name
  vpc_id            = module.networking.vpc_id
  public_subnet_ids = module.networking.public_subnet_ids
  app_subnet_ids    = module.networking.app_subnet_ids
  kms_key_arn       = module.security.kms_key_arn
  instance_type     = "t3.micro"
  desired_capacity  = 1
  min_size          = 1
  max_size          = 2
  waf_rate_limit    = 500
  tags              = local.common_tags
}

module "database" {
  source = "../../modules/database"

  name                  = local.name
  vpc_id                = module.networking.vpc_id
  subnet_ids            = module.networking.db_subnet_ids
  app_security_group_id = module.application.app_security_group_id
  kms_key_arn           = module.security.kms_key_arn
  instance_class        = "db.t4g.micro"
  multi_az              = var.database_multi_az
  deletion_protection   = var.database_deletion_protection
  tags                  = local.common_tags
}

module "detection" {
  source = "../../modules/detection"

  name        = local.name
  alert_email = var.alert_email
  tags        = local.common_tags
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
  tags                  = local.common_tags
}

