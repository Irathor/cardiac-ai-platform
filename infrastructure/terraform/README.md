# Infrastructure as Code — Terraform

Dos root modules independientes, uno por proveedor cloud. Ver ADR-6 y EPIC-9 para el contexto
completo de la decisión.

| Módulo | Proveedor | Estado |
|---|---|---|
| [`oracle/`](./oracle/) | Oracle Cloud (`oci`) | **Real, aplicado.** Despliegue de producción del proyecto. |
| [`aws/`](./aws/) | AWS (`aws`) | **Scaffold, sin aplicar.** Preparado para activar el día que el usuario decida pagarlo. |

## Por qué no hay un módulo de red/cómputo "compartido" entre ambos

Oracle Cloud y AWS usan tipos de recurso de Terraform completamente distintos (`oci_core_vcn`
vs `aws_vpc`, `oci_core_instance` vs `aws_instance`, esquemas de seguridad de red distintos:
Security List/NSG vs Security Group, autenticación completamente distinta: API signing key con
fingerprint vs access/secret key) — no hay solapamiento real de esquema que una abstracción
común pudiera capturar sin introducir una capa de indirección que solo desplazaría la
complejidad de un sitio a otro, sin reducirla (test de eliminación: si se borrara esa capa
compartida, ¿el código sería más simple o más complejo? Aquí, más simple).

Cada módulo es un root module **independiente y autocontenido**, comparable con el otro solo
por convención (mismos nombres de variables cuando el concepto es equivalente —
`ssh_allowed_cidr`, `repo_url`, `postgres_password`, etc. — y mismos nombres de outputs —
`instance_public_ip`, `sslip_hostname`, `ssh_command`), no por código Terraform compartido.

## Ambos módulos, en una frase

Una única instancia Compute (Oracle `VM.Standard.A1.Flex` ARM Ampere / AWS EC2 amd64) corriendo
el `docker-compose.yml` del repo tal cual (Caddy incluido, HTTPS automático vía Let's Encrypt
sobre un hostname `<ip-con-guiones>.sslip.io`), provisionada vía cloud-init en el primer
arranque a partir de variables Terraform `sensitive` — nunca Kubernetes/ECS/RDS gestionado, ni
multi-instancia, por alcance deliberado de EPIC-9.
