# infrastructure/terraform/oracle/outputs.tf

output "instance_public_ip" {
  description = "Public IP of the Oracle Compute instance."
  value       = oci_core_instance.app.public_ip
}

output "sslip_hostname" {
  description = <<-EOT
    Public hostname resolvable without owning a domain (EPIC-8): the
    instance's public IP with dots replaced by dashes, under the sslip.io
    wildcard DNS service, e.g. "140-238-10-5.sslip.io". Caddy uses this
    (CADDY_HOSTNAME in .env, self-derived by cloud-init at boot from the OCI
    instance metadata service, see cloud-init.tftpl) to request a real Let's
    Encrypt certificate. This output is for operator convenience only (to
    know the URL to open); cloud-init does not depend on it.
  EOT
  value       = replace(oci_core_instance.app.public_ip, ".", "-")
}

output "ssh_command" {
  description = "Convenience SSH command to reach the instance (default Canonical Ubuntu cloud image user is 'ubuntu')."
  value       = "ssh ubuntu@${oci_core_instance.app.public_ip}"
}
