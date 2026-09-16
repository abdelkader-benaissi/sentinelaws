resource "aws_security_group" "database" {
  name_prefix = "${var.name}-database-"
  description = "PostgreSQL only from the SentinelAWS application tier"
  vpc_id      = var.vpc_id

  ingress {
    description     = "PostgreSQL from application tier"
    protocol        = "tcp"
    from_port       = 5432
    to_port         = 5432
    security_groups = [var.app_security_group_id]
  }

  egress {
    description = "No application-initiated egress is expected"
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = ["127.0.0.1/32"]
  }

  tags = merge(var.tags, { Name = "${var.name}-database-sg" })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_db_subnet_group" "this" {
  name       = "${var.name}-database"
  subnet_ids = var.subnet_ids
  tags       = merge(var.tags, { Name = "${var.name}-database-subnets" })
}

resource "aws_db_instance" "this" {
  identifier = "${var.name}-postgres"

  engine         = "postgres"
  instance_class = var.instance_class
  db_name        = "sentineldb"
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
  vpc_security_group_ids = [aws_security_group.database.id]
  publicly_accessible    = false
  multi_az               = var.multi_az

  backup_retention_period    = 7
  copy_tags_to_snapshot      = true
  deletion_protection        = var.deletion_protection
  skip_final_snapshot        = !var.deletion_protection
  apply_immediately          = true
  auto_minor_version_upgrade = true

  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]

  tags = merge(var.tags, {
    Name = "${var.name}-postgres"
    Tier = "database"
  })
}

