# infrastructure/terraform/aws/main.tf
#
# SCAFFOLD ONLY — see README.md and ADR-6. This root module is never applied
# as part of this work: no terraform.tfvars, no credentials, no
# `terraform apply`/`plan` against a real AWS account anywhere in this repo
# or CI. It exists so the user can activate a paid AWS deployment later
# without designing it from scratch.
#
# Independent and self-contained from infrastructure/terraform/oracle/ on
# purpose (different provider, no shared resource types) — see ADR-6 for why
# no "shared" network/compute module was forced between the two providers.
#
# Equivalent shape to the Oracle module: a single EC2 instance running the
# same docker-compose.yml stack, no ECS/RDS/ALB — matches the Oracle
# approach's "one instance, not managed services" scope deliberately, so the
# two modules stay comparable.

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0.0, < 6.0.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# --- Networking: VPC, public subnet, internet gateway, route table -----

resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "${var.project_name}-vpc"
  }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "${var.project_name}-igw"
  }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  map_public_ip_on_launch = true
  availability_zone       = var.availability_zone

  tags = {
    Name = "${var.project_name}-public-subnet"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name = "${var.project_name}-public-rt"
  }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# --- Security group: same policy as the Oracle security list ------------
# Only 22 (restricted to ssh_allowed_cidr), 80 and 443 inbound. Every other
# service stays bound to 127.0.0.1 inside the instance (docker-compose.yml
# unchanged between providers) — this security group never needs to open
# their ports.

resource "aws_security_group" "public" {
  name        = "${var.project_name}-public-sg"
  description = "Public ingress: SSH (restricted), HTTP, HTTPS only."
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "SSH, restricted to an operator-controlled CIDR."
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.ssh_allowed_cidr]
  }

  ingress {
    description = "HTTP, redirected to HTTPS by Caddy."
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS, Caddy's real entry point."
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-public-sg"
  }
}

# --- AMI: latest Ubuntu 22.04 LTS (amd64) --------------------------------
# NOTE: EC2's free/cheap tiers (t3.micro/t2.micro) are x86_64-only in
# practice for a general-purpose Ubuntu image, so this scaffold targets
# amd64, unlike the Oracle module's ARM64 image — see README.md.

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_key_pair" "deployer" {
  key_name   = "${var.project_name}-key"
  public_key = var.ssh_public_key
}

resource "aws_instance" "app" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.public.id]
  key_name               = aws_key_pair.deployer.key_name

  root_block_device {
    volume_size = var.root_volume_size_gb
    volume_type = "gp3"
  }

  # Same cloud-init approach as the Oracle module (install Docker, clone the
  # repo, write .env from sensitive vars, docker compose up -d) — a
  # dedicated aws/cloud-init.tftpl on purpose: AWS's IMDSv2 token/metadata
  # calls and device naming differ enough from OCI's that reusing Oracle's
  # template would need provider-specific branching inside a supposedly
  # shared file, the same complexity ADR-6 avoided at the module level.
  user_data = base64encode(templatefile("${path.module}/cloud-init.tftpl", {
    repo_url               = var.repo_url
    repo_ref               = var.repo_ref
    postgres_db            = var.postgres_db
    postgres_user          = var.postgres_user
    postgres_password      = var.postgres_password
    minio_access_key       = var.minio_access_key
    minio_secret_key       = var.minio_secret_key
    jwt_secret_key         = var.jwt_secret_key
    grafana_admin_user     = var.grafana_admin_user
    grafana_admin_password = var.grafana_admin_password
    cors_allowed_origins   = var.cors_allowed_origins
    environment            = var.environment
  }))

  tags = {
    Name = "${var.project_name}-instance"
  }
}
