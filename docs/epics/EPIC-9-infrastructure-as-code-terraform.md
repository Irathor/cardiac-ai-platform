# EPIC-9: Infrastructure as Code con Terraform

## Historia de usuario
Como equipo, quiero declarar el despliegue cloud como código con Terraform, para que sea
reproducible, versionado y auditable en vez de configuración manual sobre el proveedor —
con Oracle Cloud como despliegue real aplicado, y AWS como scaffold preparado para el día
que el usuario decida pagarlo (más reconocido en un CV que Oracle Always Free).

## Tipo
Normal

## Bloqueada por
EPIC-5 (CI/CD ampliado — escaneo de dependencias + build/push de imágenes): el cloud-init de
la instancia Oracle necesita poder tirar de imágenes `backend`/`frontend` ya publicadas en
GHCR (y en su variante `arm64`, ver EPIC-8) para arrancar el stack sin tener que compilar en
la propia instancia.

## Criterios de aceptación

### Oracle (real, aplicado)
- [x] `infrastructure/terraform/oracle/` declara: VCN + subnet pública, Security List (solo
      22/80/443 entrantes), instancia Compute `VM.Standard.A1.Flex` (ARM, Always Free),
      volumen de bloque para los volúmenes con datos (Postgres/MinIO/Grafana/Prometheus), y
      un script de cloud-init (`cloud-init.tftpl`, templado con `templatefile()`) que:
      instala Docker + Docker Compose plugin, clona/actualiza el repo (o copia el
      `docker-compose.yml` + carpetas necesarias), escribe `.env` a partir de las variables
      `sensitive` de Terraform, y ejecuta `docker compose up -d`.
- [x] Todas las variables con secretos (`postgres_password`, `jwt_secret_key`,
      `minio_secret_key`, `grafana_admin_password`, etc.) están declaradas `sensitive = true`
      en `variables.tf` y se rellenan solo en un `terraform.tfvars` **no versionado**
      (`.gitignore` en `infrastructure/terraform/oracle/`) — nunca hardcodeadas en ningún
      `.tf`. `terraform.tfvars.example` documenta qué hace falta rellenar, sin valores
      reales.
- [x] Estado de Terraform en **local** (`terraform.tfstate*` en `.gitignore`), decisión
      documentada en `infrastructure/terraform/oracle/README.md` con el motivo (escala de
      un solo operador, sin equipo concurrente) y la vía de migración a un backend remoto
      (p. ej. OCI Object Storage, compatible S3) si en el futuro hiciera falta.
- [ ] `terraform apply` provisiona la instancia real usada por EPIC-8; `terraform plan`
      posterior no muestra diff (el estado declarado coincide con lo desplegado).
      **Pendiente**: requiere que el usuario aporte sus credenciales de Oracle Cloud
      (tenancy/user OCID, API key + fingerprint, compartment, región, CIDR de SSH, clave
      pública SSH, secretos de aplicación) en un `terraform.tfvars` propio (instrucciones ya
      dadas en conversación y en `infrastructure/terraform/oracle/README.md`). El resto de
      criterios de esta Epic está listo y verificado — solo falta este paso, que depende de
      una acción del usuario (creación de cuenta/credenciales), no de trabajo pendiente del
      equipo.
- [x] `outputs.tf` expone al menos la IP pública de la instancia (y el hostname
      `sslip.io` derivado, si se usa esa opción de EPIC-8).

### AWS (scaffold, sin aplicar)
- [x] `infrastructure/terraform/aws/` existe con una estructura equivalente (VPC, subnet,
      security group, instancia EC2 — mismo nivel de abstracción que `oracle/`, sin
      replicar automatismos que no aplican a AWS como el cloud-init de Oracle tal cual).
- [x] `terraform validate` pasa limpio sobre `aws/`. `terraform plan`/`apply` **no se
      ejecuta nunca** contra una cuenta real como parte de esta Epic — no hay credenciales
      de AWS en ningún sitio del repo ni en CI.
- [x] `variables.tf` de `aws/` usa valores placeholder explícitos (región, tipo de
      instancia) sin compromiso real de coste, y todo lo sensible sigue el mismo patrón
      `sensitive = true` + `.tfvars` no versionado que en `oracle/`.
- [x] `infrastructure/terraform/aws/README.md` deja explícito qué falta rellenar antes de
      poder aplicar de verdad: región concreta, tamaño de instancia real, cuenta/
      credenciales AWS, y que el coste ya no es Always Free.

### Estructura común
- [x] `infrastructure/terraform/README.md` (raíz del directorio Terraform) explica la
      relación entre ambos módulos: por qué no hay un módulo de red "compartido" entre
      Oracle y AWS (los tipos de recurso son específicos de cada provider de Terraform —
      forzar una abstracción común ahí solo trasladaría la complejidad, no la reduciría;
      ver "vocabulario de diseño" de Shepard, test de eliminación) — cada proveedor es un
      root module independiente y autocontenido, con la misma convención de nombres de
      variables/outputs para que sea fácil comparar uno con otro.

## Alcance
- `infrastructure/terraform/oracle/` (real): `main.tf`, `variables.tf`, `outputs.tf`,
  `cloud-init.tftpl`, `terraform.tfvars.example`, `README.md`.
- `infrastructure/terraform/aws/` (scaffold): misma composición de archivos, sin aplicar.
- `infrastructure/terraform/README.md`.
- No toca `docker-compose.yml` en sí más allá de lo que EPIC-8 ya cambia (Caddy) — el
  cloud-init reutiliza el compose del repo tal cual, no lo reescribe.

## Fuera de alcance
- `terraform apply` real sobre AWS (queda para cuando el usuario decida pagarlo).
- Multi-entorno (dev/staging/prod separados), salvo que se pida después.
- Backend remoto de estado de Terraform para Oracle (documentado como vía de migración
  futura, no implementado ahora).
- Cualquier orquestador más allá de Docker Compose (Kubernetes, ECS gestionado, etc.) — el
  scaffold de `aws/` usa EC2 + Docker Compose, coherente con el resto del proyecto, no un
  rediseño a otro modelo de despliegue.

## Verificación (parcial — checkpoint intermedio, no cierre)
- `terraform init -backend=false` + `terraform validate` reales sobre ambos módulos,
  re-ejecutados de forma independiente por el orquestador (no solo aceptados del informe de
  Garrus): `oracle/` contra el provider real `oracle/oci` v5.47.0 y `aws/` contra
  `hashicorp/aws` v5.100.0 — ambos "Success! The configuration is valid."
- `bash -n` sobre ambos `cloud-init.tftpl` renderizados (placeholders sustituidos): sintaxis
  válida.
- `security-review`: 1 hallazgo real MEDIUM compartido con EPIC-8 (heredoc de cloud-init sin
  comillas, permitía inyección de comandos vía valores de secreto) — corregido en ambos
  módulos (`oracle/` y `aws/`) en este checkpoint, verificado funcionalmente con un caso
  malicioso simulado: el payload queda escrito literalmente en `.env`, nunca se ejecuta.
  Resto sin hallazgos bloqueantes.
- Pendiente para cerrar de verdad: `terraform apply` real contra Oracle Cloud, bloqueado
  únicamente en que el usuario aporte sus credenciales — no hay trabajo de implementación
  pendiente del equipo.

## Estado
En progreso
