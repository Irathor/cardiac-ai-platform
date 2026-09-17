# infrastructure/terraform/aws/variables.tf
#
# Scaffold only (ADR-6): placeholder values below are explicit and
# non-committal about cost — none of this is applied. Sensitive variables
# follow the exact same sensitive = true / no-default pattern as
# oracle/variables.tf, even though this module is never actually run with
# real values in this repo.

variable "aws_region" {
  description = "AWS region to deploy into. Placeholder only — pick based on latency/cost once this scaffold is activated."
  type        = string
  default     = "eu-west-1"
}

variable "availability_zone" {
  description = "AWS availability zone for the public subnet."
  type        = string
  default     = "eu-west-1a"
}

variable "project_name" {
  description = "Short name prefix applied to every resource's Name tag."
  type        = string
  default     = "cardiac-ai"
}

variable "instance_type" {
  description = <<-EOT
    EC2 instance type. Placeholder only, NOT a cost commitment: t2.micro/
    t3.micro are the 12-month free-tier eligible types but (per ADR-6) don't
    have enough RAM (1GB) for this stack. A real activation of this scaffold
    needs a paid type, e.g. t3.medium (4GB) or larger, sized against the
    stack's actual memory usage before committing to a size.
  EOT
  type        = string
  default     = "t3.micro"
}

variable "root_volume_size_gb" {
  description = "Root EBS volume size in GB (holds everything, no separate data volume in this scaffold — unlike Oracle's dedicated block volume)."
  type        = number
  default     = 30
}

variable "ssh_allowed_cidr" {
  description = "CIDR allowed to reach port 22. Never defaults to 0.0.0.0/0 — set explicitly to an operator-controlled CIDR when this scaffold is activated."
  type        = string
  default     = "203.0.113.0/32"
}

variable "ssh_public_key" {
  description = "Public SSH key (contents, not a path) authorized to log into the instance."
  type        = string
  default     = "ssh-ed25519 AAAA... placeholder-not-a-real-key"
}

variable "repo_url" {
  description = "Git URL cloud-init clones on first boot."
  type        = string
  default     = "https://github.com/<your-github-user>/cardiac-ai-platform.git"
}

variable "repo_ref" {
  description = "Git ref (branch, tag, or commit) to check out on first boot."
  type        = string
  default     = "master"
}

variable "environment" {
  description = "Value written to ENVIRONMENT in the generated .env."
  type        = string
  default     = "production"
}

variable "cors_allowed_origins" {
  description = "Value written to CORS_ALLOWED_ORIGINS in the generated .env."
  type        = string
  default     = "https://<ip-with-dashes>.sslip.io"
}

# --- Secrets: sensitive = true, no default, same pattern as oracle/ ------

variable "postgres_db" {
  description = "Value written to POSTGRES_DB in the generated .env."
  type        = string
  default     = "cardiac_ai"
}

variable "postgres_user" {
  description = "Value written to POSTGRES_USER in the generated .env."
  type        = string
  default     = "cardiac_ai"
}

variable "postgres_password" {
  description = "Value written to POSTGRES_PASSWORD in the generated .env. No default, same sensitive/no-default pattern as oracle/variables.tf — must come from a (never-applied) terraform.tfvars."
  type        = string
  sensitive   = true
}

variable "minio_access_key" {
  description = "Value written to MINIO_ACCESS_KEY in the generated .env."
  type        = string
  sensitive   = true
}

variable "minio_secret_key" {
  description = "Value written to MINIO_SECRET_KEY in the generated .env."
  type        = string
  sensitive   = true
}

variable "jwt_secret_key" {
  description = "Value written to JWT_SECRET_KEY in the generated .env."
  type        = string
  sensitive   = true
}

variable "grafana_admin_user" {
  description = "Value written to GRAFANA_ADMIN_USER in the generated .env."
  type        = string
  default     = "admin"
}

variable "grafana_admin_password" {
  description = "Value written to GRAFANA_ADMIN_PASSWORD in the generated .env."
  type        = string
  sensitive   = true
}
