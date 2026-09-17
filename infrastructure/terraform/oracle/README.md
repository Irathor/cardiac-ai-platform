# Terraform — Oracle Cloud (real, aplicado)

Provisiona el despliegue real del stack completo (`docker-compose.yml` del repo, sin fork
paralelo) sobre una única instancia Oracle Cloud **Always Free** (`VM.Standard.A1.Flex`, ARM
Ampere, hasta 4 OCPU / 24GB RAM gratis de forma indefinida), con Caddy sirviendo HTTPS real
vía Let's Encrypt sobre un hostname `sslip.io`. Ver ADR-6 y EPIC-8/EPIC-9 para el contexto de
la decisión.

## Qué provisiona

- VCN + subnet pública + tabla de rutas + internet gateway.
- Security List abierta solo a 22 (SSH, restringido a `ssh_allowed_cidr`), 80 y 443.
- Instancia Compute `VM.Standard.A1.Flex` (imagen Canonical Ubuntu ARM64).
- Volumen de bloque dedicado, montado en `/var/lib/docker` en el primer arranque, para que los
  datos con estado (Postgres/MinIO/Prometheus/Grafana) no compitan con el volumen de arranque.
- `cloud-init.tftpl`: instala Docker + Docker Compose plugin, clona el repo, escribe `.env` a
  partir de las variables `sensitive` de Terraform, y ejecuta `docker compose up -d --build`.

## Credenciales de Oracle Cloud que hacen falta

Ninguna de estas credenciales vive en este repo ni las tiene Garrus/el equipo — las aporta el
usuario en su propio `terraform.tfvars` (nunca versionado, ver `.gitignore`).

1. **Cuenta Oracle Cloud** con el tier Always Free activo:
   https://www.oracle.com/cloud/free/
2. **Tenancy OCID**: consola OCI → menú de perfil (esquina superior derecha) → "Tenancy: <nombre>".
   Documentación: https://docs.oracle.com/en-us/iaas/Content/GSG/Tasks/contactingsupport_topic-Locating_Oracle_Cloud_Infrastructure_IDs.htm
3. **User OCID**: consola OCI → menú de perfil → "User Settings" → OCID del usuario.
4. **API signing key + fingerprint**: consola OCI → "User Settings" → "API Keys" → "Add API
   Key" → genera un par de claves (o sube una pública propia). Oracle muestra el `fingerprint`
   al confirmar; la clave privada (`.pem`) se descarga una sola vez y se queda en la máquina
   del operador (`private_key_path` apunta a esa ruta local, la clave en sí nunca se comitea).
   Documentación: https://docs.oracle.com/en-us/iaas/Content/API/Concepts/apisigningkey.htm
5. **Compartment OCID**: puede ser el mismo que `tenancy_ocid` para una cuenta de un solo
   operador sin compartimentos adicionales, o el OCID de un compartment específico si se creó
   uno.
6. **Región**: la región OCI donde se tiene cuota Always Free (p. ej. `eu-madrid-1`,
   `us-ashburn-1`) — la disponibilidad de capacidad A1.Flex Always Free varía por región/AD,
   si `terraform apply` falla por falta de capacidad en una AD, reintentar o probar otra
   región es un problema conocido de Oracle Always Free, no de este Terraform.
7. **Clave SSH pública propia** (`ssh_public_key`) y **tu IP pública** en CIDR
   (`ssh_allowed_cidr`, ej. `203.0.113.10/32`, obtenible con `curl -s ifconfig.me`).
8. **URL del repo** (`repo_url`) que cloud-init clona en el primer arranque.
9. **Secretos de aplicación**: `postgres_password`, `minio_access_key`, `minio_secret_key`,
   `jwt_secret_key`, `grafana_admin_password` — los mismos que usarías en un `.env` local, ver
   `.env.example` en la raíz del repo.

## Comandos

```bash
cd infrastructure/terraform/oracle
cp terraform.tfvars.example terraform.tfvars
# editar terraform.tfvars con los valores reales (nunca comitear este archivo)

terraform init
terraform plan
terraform apply
```

Tras un `apply` correcto, `terraform plan` posterior no debe mostrar diff — si lo muestra, hay
un drift entre lo declarado y lo desplegado que hay que investigar antes de dar el despliegue
por estable.

La IP pública y el hostname `sslip.io` derivado quedan en los outputs (`terraform output`).

## Estado de Terraform

El `terraform.tfstate*` vive **en local** (gitignored), no en un backend remoto. Decisión
adecuada a la escala actual: un solo operador, sin equipo concurrente tocando la
infraestructura. Si en el futuro hace falta colaboración concurrente sobre el mismo estado, la
vía de migración natural es un backend remoto compatible S3 sobre **OCI Object Storage**
(soporta el protocolo S3, se puede usar como backend `s3` de Terraform apuntando al endpoint de
OCI) — no implementado ahora, ver `docs/BACKLOG.md`.

## Lo que NO se pudo verificar en este entorno

Este trabajo se hizo sin el binario `terraform` disponible ni acceso de red al Terraform
Registry en el sandbox donde se escribió. La sintaxis de recursos/atributos del provider `oci`
(`oci_core_vcn`, `oci_core_instance`, `shape_config`, `source_details`,
`oci_core_volume_attachment` con `attachment_type = "paravirtualized"`, el alias de dispositivo
`/dev/oracleoci/oraclevdb`, el endpoint IMDS `http://169.254.169.254/opc/v2/vnics/`) se escribió
con la mayor confianza posible a partir de la documentación conocida de Hashicorp/Oracle, **sin
poder correr `terraform init`/`validate`/`plan` contra el provider real**. Antes del primer
`terraform apply` real, ejecuta tú mismo `terraform init && terraform validate` — es la primera
verificación barata que falta y que este sandbox no pudo hacer por ti.
