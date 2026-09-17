# infrastructure/terraform/aws/outputs.tf
# Same output names as oracle/outputs.tf by convention, for easy comparison.

output "instance_public_ip" {
  description = "Public IP of the EC2 instance."
  value       = aws_instance.app.public_ip
}

output "sslip_hostname" {
  description = "Public hostname resolvable without owning a domain (see oracle/outputs.tf for the same convention)."
  value       = replace(aws_instance.app.public_ip, ".", "-")
}

output "ssh_command" {
  description = "Convenience SSH command to reach the instance (default Canonical Ubuntu cloud image user is 'ubuntu')."
  value       = "ssh ubuntu@${aws_instance.app.public_ip}"
}
