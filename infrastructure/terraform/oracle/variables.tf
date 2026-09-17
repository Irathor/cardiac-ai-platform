# infrastructure/terraform/oracle/variables.tf
#
# All variables below have no default for anything OCI-account-specific or
# secret — they must be supplied via terraform.tfvars (copy
# terraform.tfvars.example, never commit the real file — see .gitignore).

# --- OCI account / API credentials --------------------------------------
# See README.md for exactly how to obtain each of these from the Oracle
# Cloud console.

variable "tenancy_ocid" {
  description = "OCID of the OCI tenancy (root compartment). Console: Profile menu > Tenancy."
  type        = string
  sensitive   = true
}

variable "user_ocid" {
  description = "OCID of the OCI user Terraform authenticates as. Console: Profile menu > User Settings."
  type        = string
  sensitive   = true
}

variable "fingerprint" {
  description = "Fingerprint of the API signing key uploaded to the OCI user (Console: User Settings > API Keys)."
  type        = string
  sensitive   = true
}

variable "private_key_path" {
  description = "Local filesystem path to the PEM private key matching the uploaded API key's fingerprint. The key file itself never lives in this repo."
  type        = string
  sensitive   = true
}

variable "compartment_ocid" {
  description = "OCID of the compartment to provision resources into (can be the tenancy OCID itself for a single-operator setup)."
  type        = string
  sensitive   = true
}

variable "region" {
  description = "OCI region to deploy into (e.g. \"eu-madrid-1\", \"us-ashburn-1\"). Always Free A1.Flex capacity varies by region/availability domain."
  type        = string
}

# --- Instance sizing (Always Free A1.Flex: up to 4 OCPU / 24GB total) ---

variable "project_name" {
  description = "Short name prefix applied to every resource's display_name for easy identification in the OCI console."
  type        = string
  default     = "cardiac-ai"
}

variable "instance_ocpus" {
  description = "OCPUs allocated to the A1.Flex instance. Always Free covers up to 4 total."
  type        = number
  default     = 4
}

variable "instance_memory_gbs" {
  description = "Memory (GB) allocated to the A1.Flex instance. Always Free covers up to 24 total."
  type        = number
  default     = 24
}

variable "boot_volume_size_gb" {
  description = "Boot volume size in GB. Counts against the Always Free 200GB total block storage allowance shared with data_volume_size_gb."
  type        = number
  default     = 50
}

variable "data_volume_size_gb" {
  description = "Size (GB) of the dedicated block volume mounted at /var/lib/docker for stateful container data (Postgres/MinIO/Prometheus/Grafana volumes)."
  type        = number
  default     = 100
}

variable "ubuntu_version" {
  description = "Canonical Ubuntu version to look up an ARM64 image for (must have an official arm64 build for VM.Standard.A1.Flex)."
  type        = string
  default     = "22.04"
}

# --- Network access ------------------------------------------------------

variable "ssh_allowed_cidr" {
  description = <<-EOT
    CIDR allowed to reach port 22. Oracle Cloud Always Free gives no static/
    reserved IP for the operator's own machine, so this can't default to a
    single known address; set it to "<your-public-ip>/32" and update it if
    your IP changes. 0.0.0.0/0 is deliberately NOT the default — if you truly
    have no stable IP and need it open to any source, set it explicitly and
    treat that as an accepted, documented risk, not an oversight.
  EOT
  type        = string
}

variable "ssh_public_key" {
  description = "Public SSH key (contents, not a path) authorized to log into the instance as the default user. Not a secret by nature, but keep it out of shared tfvars files you don't control."
  type        = string
}

# --- Application deployment ----------------------------------------------

variable "repo_url" {
  description = "Git URL cloud-init clones on first boot to obtain docker-compose.yml and the infrastructure/ folder (e.g. https://github.com/<user>/cardiac-ai-platform.git)."
  type        = string
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
  description = "Value written to CORS_ALLOWED_ORIGINS in the generated .env (the public HTTPS origin once the sslip.io hostname is known, e.g. https://140-238-10-5.sslip.io)."
  type        = string
}

# --- Secrets (never hardcoded, never defaulted) --------------------------

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
  description = "Value written to POSTGRES_PASSWORD in the generated .env."
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
  description = "Value written to JWT_SECRET_KEY in the generated .env. Generate with: python -c \"import secrets; print(secrets.token_urlsafe(64))\"."
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
