data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_region" "current" {}

data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-x86_64"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

locals {
  application_source = base64gzip(file("${path.module}/../../../app/server.py"))
  requirements       = base64encode(file("${path.module}/../../../app/requirements.txt"))
}

#checkov:skip=CKV_AWS_260:Port 80 accepts no application traffic and only redirects to HTTPS.
resource "aws_security_group" "alb" {
  name_prefix = "${var.name}-alb-"
  description = "Public HTTPS entry point with HTTP redirect"
  vpc_id      = var.vpc_id

  ingress {
    description = "HTTPS from internet"
    protocol    = "tcp"
    from_port   = 443
    to_port     = 443
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTP redirect to HTTPS"
    protocol    = "tcp"
    from_port   = 80
    to_port     = 80
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description     = "Application traffic to private instances"
    protocol        = "tcp"
    from_port       = 8080
    to_port         = 8080
    security_groups = [var.app_security_group_id]
  }

  tags = merge(var.tags, { Name = "${var.name}-alb-sg" })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_s3_bucket" "alb_logs" {
  bucket_prefix = "${var.name}-alb-logs-"
  force_destroy = var.force_destroy_logs
  tags          = merge(var.tags, { DataClassification = "access-log" })
}

resource "aws_s3_bucket_public_access_block" "alb_logs" {
  bucket = aws_s3_bucket.alb_logs.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "alb_logs" {
  bucket = aws_s3_bucket.alb_logs.id
  rule { object_ownership = "BucketOwnerEnforced" }
}

resource "aws_s3_bucket_versioning" "alb_logs" {
  bucket = aws_s3_bucket.alb_logs.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "alb_logs" {
  bucket = aws_s3_bucket.alb_logs.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "alb_logs" {
  bucket = aws_s3_bucket.alb_logs.id
  rule {
    id     = "access-log-retention"
    status = "Enabled"
    filter {}
    expiration { days = var.access_log_retention_days }
    abort_incomplete_multipart_upload { days_after_initiation = 7 }
  }
}

resource "aws_s3_bucket_notification" "alb_logs" {
  bucket      = aws_s3_bucket.alb_logs.id
  eventbridge = true
}

data "aws_iam_policy_document" "alb_logs" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.alb_logs.arn, "${aws_s3_bucket.alb_logs.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }

  statement {
    sid       = "AllowALBLogDelivery"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.alb_logs.arn}/AWSLogs/${data.aws_caller_identity.current.account_id}/*"]
    principals {
      type        = "Service"
      identifiers = ["logdelivery.elasticloadbalancing.amazonaws.com"]
    }
  }
}

resource "aws_s3_bucket_policy" "alb_logs" {
  bucket = aws_s3_bucket.alb_logs.id
  policy = data.aws_iam_policy_document.alb_logs.json
}

resource "aws_lb" "this" {
  name               = substr("${var.name}-alb", 0, 32)
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = var.public_subnet_ids

  enable_deletion_protection = var.enable_deletion_protection
  drop_invalid_header_fields = true

  access_logs {
    bucket  = aws_s3_bucket.alb_logs.id
    enabled = true
  }

  depends_on = [aws_s3_bucket_policy.alb_logs]
  tags       = merge(var.tags, { Name = "${var.name}-alb" })
}

resource "aws_lb_target_group" "app" {
  name        = substr("${var.name}-app", 0, 32)
  port        = 8080
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "instance"

  health_check {
    enabled             = true
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    matcher             = "200"
  }

  tags = var.tags
}

resource "aws_lb_listener" "http_redirect" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "app" {
  name               = "${var.name}-app-instance"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.app.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "database_secret" {
  statement {
    sid       = "ReadOnlyRDSCredential"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.db_secret_arn]
  }

  statement {
    sid       = "DecryptRDSCredential"
    actions   = ["kms:Decrypt"]
    resources = [var.kms_key_arn]
  }
}

resource "aws_iam_role_policy" "database_secret" {
  name   = "read-rds-credential"
  role   = aws_iam_role.app.id
  policy = data.aws_iam_policy_document.database_secret.json
}

resource "aws_iam_instance_profile" "app" {
  name = "${var.name}-app-instance"
  role = aws_iam_role.app.name
}

resource "aws_launch_template" "app" {
  name_prefix   = "${var.name}-app-"
  image_id      = data.aws_ami.amazon_linux.id
  instance_type = var.instance_type

  iam_instance_profile { arn = aws_iam_instance_profile.app.arn }

  network_interfaces {
    associate_public_ip_address = false
    security_groups             = [var.app_security_group_id]
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
    instance_metadata_tags      = "enabled"
  }

  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      volume_size           = 8
      volume_type           = "gp3"
      encrypted             = true
      kms_key_id            = var.kms_key_arn
      delete_on_termination = true
    }
  }

  user_data = base64encode(<<-USERDATA
    #!/bin/bash
    set -euo pipefail
    dnf install -y python3-pip
    install -d -m 0755 /opt/sentinelaws
    echo '${local.application_source}' | base64 -d | gzip -d > /opt/sentinelaws/server.py
    echo '${local.requirements}' | base64 -d > /opt/sentinelaws/requirements.txt
    python3 -m venv /opt/sentinelaws/venv
    /opt/sentinelaws/venv/bin/pip install --no-cache-dir -r /opt/sentinelaws/requirements.txt
    chown -R root:root /opt/sentinelaws
    chmod -R go-w /opt/sentinelaws

    cat > /etc/systemd/system/sentinelaws.service <<'UNIT'
    [Unit]
    Description=SentinelAWS demonstration application
    After=network-online.target
    Wants=network-online.target

    [Service]
    Type=simple
    User=nobody
    Environment=ENVIRONMENT=${var.environment}
    Environment=AWS_REGION=${data.aws_region.current.name}
    Environment=DB_HOST=${var.db_endpoint}
    Environment=DB_NAME=${var.db_name}
    Environment=DB_SECRET_ARN=${var.db_secret_arn}
    ExecStart=/opt/sentinelaws/venv/bin/python /opt/sentinelaws/server.py
    Restart=always
    RestartSec=5
    NoNewPrivileges=true
    PrivateTmp=true
    ProtectSystem=strict
    ProtectHome=true

    [Install]
    WantedBy=multi-user.target
    UNIT

    systemctl daemon-reload
    systemctl enable --now sentinelaws.service
  USERDATA
  )

  tag_specifications {
    resource_type = "instance"
    tags = merge(var.tags, {
      Name               = "${var.name}-app"
      Tier               = "application"
      SentinelAWSManaged = "true"
    })
  }

  tag_specifications {
    resource_type = "volume"
    tags          = merge(var.tags, { Name = "${var.name}-app-volume" })
  }

  update_default_version = true

  lifecycle { create_before_destroy = true }
}

resource "aws_autoscaling_group" "app" {
  name                      = "${var.name}-app"
  vpc_zone_identifier       = var.app_subnet_ids
  desired_capacity          = var.desired_capacity
  min_size                  = var.min_size
  max_size                  = var.max_size
  health_check_type         = "ELB"
  health_check_grace_period = 300
  target_group_arns         = [aws_lb_target_group.app.arn]

  launch_template {
    id      = aws_launch_template.app.id
    version = "$Latest"
  }

  instance_refresh {
    strategy = "Rolling"
    preferences { min_healthy_percentage = 50 }
    triggers = ["tag"]
  }

  dynamic "tag" {
    for_each = merge(var.tags, { SentinelAWSManaged = "true" })
    content {
      key                 = tag.key
      value               = tag.value
      propagate_at_launch = true
    }
  }
}

resource "aws_autoscaling_policy" "cpu" {
  name                   = "${var.name}-cpu-target"
  autoscaling_group_name = aws_autoscaling_group.app.name
  policy_type            = "TargetTrackingScaling"

  target_tracking_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ASGAverageCPUUtilization"
    }
    target_value = 60
  }
}

resource "aws_wafv2_ip_set" "incident_blocklist" {
  name               = "${var.name}-incident-blocklist"
  description        = "Public IPv4 addresses added by controlled response automation"
  scope              = "REGIONAL"
  ip_address_version = "IPV4"
  addresses          = []
  tags               = var.tags

  lifecycle { ignore_changes = [addresses] }
}

resource "aws_wafv2_web_acl" "this" {
  name        = "${var.name}-web-acl"
  description = "Defense-in-depth controls for the SentinelAWS ALB"
  scope       = "REGIONAL"

  default_action {
    allow {}
  }

  rule {
    name     = "incident-blocklist"
    priority = 0
    action {
      block {}
    }
    statement {
      ip_set_reference_statement {
        arn = aws_wafv2_ip_set.incident_blocklist.arn
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "incident-blocklist"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "aws-known-bad-inputs"
    priority = 10
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "aws-known-bad-inputs"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "aws-common-rules"
    priority = 20
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "aws-common-rules"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "aws-anonymous-ip-list"
    priority = 25
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesAnonymousIpList"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "aws-anonymous-ip-list"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "rate-limit"
    priority = 30
    action {
      block {}
    }
    statement {
      rate_based_statement {
        aggregate_key_type = "IP"
        limit              = var.waf_rate_limit
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "rate-limit"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.name}-web-acl"
    sampled_requests_enabled   = true
  }

  tags = var.tags
}

resource "aws_wafv2_web_acl_association" "alb" {
  resource_arn = aws_lb.this.arn
  web_acl_arn  = aws_wafv2_web_acl.this.arn
}

resource "aws_cloudwatch_log_group" "waf" {
  name              = "aws-waf-logs-${var.name}"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.kms_key_arn
  tags              = var.tags
}

resource "aws_wafv2_web_acl_logging_configuration" "this" {
  log_destination_configs = [aws_cloudwatch_log_group.waf.arn]
  resource_arn            = aws_wafv2_web_acl.this.arn

  redacted_fields {
    single_header {
      name = "authorization"
    }
  }
  redacted_fields {
    single_header {
      name = "cookie"
    }
  }
}
