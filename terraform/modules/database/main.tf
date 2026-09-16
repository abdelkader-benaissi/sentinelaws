data "aws_partition" "current" {}

locals {
  identifier = "${var.name}-postgres"
}

resource "aws_security_group" "database" {
  name_prefix            = "${var.name}-database-"
  description            = "PostgreSQL only from the SentinelAWS application tier"
  vpc_id                 = var.vpc_id
  revoke_rules_on_delete = true

  ingress {
    description     = "PostgreSQL from application tier"
    protocol        = "tcp"
    from_port       = 5432
    to_port         = 5432
    security_groups = [var.app_security_group_id]
  }

  tags = merge(var.tags, { Name = "${var.name}-database-sg" })

  lifecycle { create_before_destroy = true }
}

resource "aws_db_subnet_group" "this" {
  name       = "${var.name}-database"
  subnet_ids = var.subnet_ids
  tags       = merge(var.tags, { Name = "${var.name}-database-subnets" })
}

resource "aws_db_parameter_group" "this" {
  name   = "${var.name}-postgres16"
  family = "postgres16"

  parameter {
    name  = "log_connections"
    value = "1"
  }

  parameter {
    name  = "log_disconnections"
    value = "1"
  }

  parameter {
    name  = "log_statement"
    value = "ddl"
  }

  parameter {
    name  = "log_min_duration_statement"
    value = "1000"
  }

  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }

  tags = var.tags
}

data "aws_iam_policy_document" "monitoring_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["monitoring.rds.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "monitoring" {
  name               = "${var.name}-rds-monitoring"
  assume_role_policy = data.aws_iam_policy_document.monitoring_assume.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "monitoring" {
  role       = aws_iam_role.monitoring.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}

resource "aws_cloudwatch_log_group" "postgresql" {
  name              = "/aws/rds/instance/${local.identifier}/postgresql"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.kms_key_arn
  tags              = var.tags
}

resource "aws_cloudwatch_log_group" "upgrade" {
  name              = "/aws/rds/instance/${local.identifier}/upgrade"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.kms_key_arn
  tags              = var.tags
}

#checkov:skip=CKV_AWS_157:Multi-AZ is controlled by the explicit lab or HA deployment profile.
resource "aws_db_instance" "this" {
  identifier = local.identifier

  engine         = "postgres"
  engine_version = "16"
  instance_class = var.instance_class
  db_name        = var.db_name
  username       = "sentineladmin"
  port           = 5432

  allocated_storage     = 20
  max_allocated_storage = 100
  storage_type          = "gp3"
  storage_encrypted     = true
  kms_key_id            = var.kms_key_arn

  manage_master_user_password   = true
  master_user_secret_kms_key_id = var.kms_key_arn

  db_subnet_group_name   = aws_db_subnet_group.this.name
  parameter_group_name   = aws_db_parameter_group.this.name
  vpc_security_group_ids = [aws_security_group.database.id]
  publicly_accessible    = false
  multi_az               = var.multi_az

  iam_database_authentication_enabled = true
  monitoring_interval                   = 60
  monitoring_role_arn                   = aws_iam_role.monitoring.arn
  performance_insights_enabled          = true
  performance_insights_kms_key_id       = var.kms_key_arn
  performance_insights_retention_period = 7

  backup_retention_period    = 7
  copy_tags_to_snapshot      = true
  deletion_protection        = var.deletion_protection
  skip_final_snapshot        = !var.deletion_protection
  final_snapshot_identifier  = var.deletion_protection ? "${var.name}-final" : null
  apply_immediately          = var.apply_immediately
  auto_minor_version_upgrade = true

  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]

  depends_on = [
    aws_cloudwatch_log_group.postgresql,
    aws_cloudwatch_log_group.upgrade,
    aws_iam_role_policy_attachment.monitoring,
  ]

  tags = merge(var.tags, {
    Name = local.identifier
    Tier = "database"
  })
}
