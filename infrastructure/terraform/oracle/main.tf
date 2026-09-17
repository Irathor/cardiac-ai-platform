# infrastructure/terraform/oracle/main.tf
#
# Real, applied deployment target (EPIC-8/EPIC-9, ADR-6): a single Oracle Cloud
# Always Free Compute instance (VM.Standard.A1.Flex, ARM Ampere) running the
# repo's docker-compose.yml stack behind Caddy.
#
# Provider syntax below follows the official `oracle/oci` Terraform provider
# (registry.terraform.io/providers/oracle/oci). `terraform init`/`validate`
# against the real provider schema (oracle/oci v5.47.0) passed clean at
# EPIC-8/EPIC-9's close checkpoint — see the Epic's "Verificación" section
# for the exact commands run. `terraform apply` was never run (needs the
# operator's own Oracle Cloud credentials, see README.md in this directory).

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    oci = {
      source  = "oracle/oci"
      version = ">= 5.0.0, < 6.0.0"
    }
  }
}

provider "oci" {
  tenancy_ocid     = var.tenancy_ocid
  user_ocid        = var.user_ocid
  fingerprint      = var.fingerprint
  private_key_path = var.private_key_path
  region           = var.region
}

# --- Availability domain -----------------------------------------------

data "oci_identity_availability_domains" "ads" {
  compartment_id = var.tenancy_ocid
}

# --- Networking: VCN, gateway, route table, security list, subnet ------

resource "oci_core_vcn" "main" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.0.0.0/16"]
  display_name   = "${var.project_name}-vcn"
  dns_label      = "cardiacai"
}

resource "oci_core_internet_gateway" "main" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = "${var.project_name}-igw"
  enabled        = true
}

resource "oci_core_route_table" "main" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = "${var.project_name}-public-rt"

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.main.id
  }
}

# Only 22 (restricted to var.ssh_allowed_cidr, never 0.0.0.0/0), 80 and 443
# are open. Every other service (postgres/redis/minio/mlflow/prometheus/
# grafana) stays bound to 127.0.0.1 on the instance itself (see
# docker-compose.yml) — this security list never needs to open their ports,
# admin access goes through an SSH tunnel instead.
resource "oci_core_security_list" "public" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = "${var.project_name}-public-sl"

  egress_security_rules {
    destination = "0.0.0.0/0"
    protocol    = "all"
  }

  ingress_security_rules {
    protocol    = "6" # TCP
    source      = var.ssh_allowed_cidr
    description = "SSH, restricted to an operator-controlled CIDR (see variables.tf)."
    tcp_options {
      min = 22
      max = 22
    }
  }

  ingress_security_rules {
    protocol    = "6"
    source      = "0.0.0.0/0"
    description = "HTTP, redirected to HTTPS by Caddy."
    tcp_options {
      min = 80
      max = 80
    }
  }

  ingress_security_rules {
    protocol    = "6"
    source      = "0.0.0.0/0"
    description = "HTTPS, Caddy's real entry point."
    tcp_options {
      min = 443
      max = 443
    }
  }
}

resource "oci_core_subnet" "public" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.main.id
  cidr_block                 = "10.0.1.0/24"
  display_name               = "${var.project_name}-public-subnet"
  dns_label                  = "public"
  route_table_id             = oci_core_route_table.main.id
  security_list_ids          = [oci_core_security_list.public.id]
  prohibit_public_ip_on_vnic = false
}

# --- Boot image: Canonical Ubuntu, ARM64 build for the A1 shape --------

data "oci_core_images" "ubuntu_arm" {
  compartment_id           = var.compartment_ocid
  operating_system         = "Canonical Ubuntu"
  operating_system_version = var.ubuntu_version
  shape                    = "VM.Standard.A1.Flex"
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}

# --- Block volume for stateful data (Postgres/MinIO/Prometheus/Grafana) -
#
# Mounted at /var/lib/docker (see cloud-init.tftpl) so all named Docker
# volumes declared in docker-compose.yml land on this dedicated volume
# instead of the (smaller) boot volume — keeps the boot volume free for the
# OS/Docker images and makes the data volume easy to reason about/resize on
# its own within the Always Free 200GB total block storage allowance.
resource "oci_core_volume" "data" {
  compartment_id      = var.compartment_ocid
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  display_name        = "${var.project_name}-data-volume"
  size_in_gbs         = var.data_volume_size_gb
}

# --- Compute instance ----------------------------------------------------

resource "oci_core_instance" "app" {
  compartment_id      = var.compartment_ocid
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  display_name        = "${var.project_name}-instance"
  shape               = "VM.Standard.A1.Flex"

  # Always Free covers up to 4 OCPU / 24GB RAM total across A1.Flex
  # instances. Defaults below use the full allowance for a single instance;
  # override via terraform.tfvars if splitting across more than one.
  shape_config {
    ocpus         = var.instance_ocpus
    memory_in_gbs = var.instance_memory_gbs
  }

  source_details {
    source_type             = "image"
    source_id               = data.oci_core_images.ubuntu_arm.images[0].id
    boot_volume_size_in_gbs = var.boot_volume_size_gb
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.public.id
    assign_public_ip = true
    display_name     = "${var.project_name}-vnic"
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key

    # cloud-init runs as plain user-data (shebang script, not #cloud-config
    # YAML) — see cloud-init.tftpl for why (needs real control flow: device
    # wait loops, IMDS lookup for the instance's own public IP).
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
  }
}

resource "oci_core_volume_attachment" "data" {
  attachment_type = "paravirtualized"
  instance_id     = oci_core_instance.app.id
  volume_id       = oci_core_volume.data.id
  device          = "/dev/oracleoci/oraclevdb"

  # cloud-init waits for and mounts this device on first boot — the instance
  # must exist before the volume can attach, and the attachment must exist
  # before cloud-init's mount step can succeed, hence this explicit ordering.
  depends_on = [oci_core_instance.app]
}
