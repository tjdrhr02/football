# Reuse the account's default VPC + subnets — no VPC creation (simpler, free).
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_db_subnet_group" "this" {
  name       = "${var.project}-db-subnets"
  subnet_ids = data.aws_subnets.default.ids

  tags = { Project = var.project }
}

# Allow Postgres (5432) only from your own IP. Egress open (for minor version pulls etc).
resource "aws_security_group" "db" {
  name        = "${var.project}-rds-sg"
  description = "Allow Postgres from my IP only"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "Postgres from my IP"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [var.my_ip]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Project = var.project }
}

resource "aws_db_instance" "this" {
  identifier     = "${var.project}-rds"
  engine         = "postgres"
  engine_version = var.engine_version

  # --- Free-tier sizing (see infra/terraform/README.md cost guardrails) ---
  instance_class        = "db.t4g.micro" # free tier 750h/month
  allocated_storage     = 20             # free tier max (gp2)
  max_allocated_storage = 0              # disable storage autoscaling -> no surprise charges
  storage_type          = "gp2"

  db_name  = var.db_name
  username = var.db_username
  password = var.db_password
  port     = 5432

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.db.id]
  publicly_accessible    = true

  multi_az                    = false # Multi-AZ is paid
  backup_retention_period     = 1     # tiny DB -> within free 20GB backup
  performance_insights_enabled = false
  monitoring_interval         = 0     # no Enhanced Monitoring (avoids CloudWatch cost)
  auto_minor_version_upgrade  = true

  # Easy teardown for a sandbox/portfolio DB
  deletion_protection = false
  skip_final_snapshot = true
  apply_immediately   = true

  tags = { Project = var.project }
}
