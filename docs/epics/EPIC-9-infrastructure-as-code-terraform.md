# EPIC-9: Infrastructure as Code con Terraform

## Historia de usuario
Como equipo, quiero declarar el despliegue cloud como código con Terraform, para que sea
reproducible, versionado y auditable en vez de configuración manual sobre el proveedor.

## Tipo
Normal

## Bloqueada por
EPIC-8 (Deployment cloud).

## Criterios de aceptación
- [ ] El mismo despliegue de EPIC-8 queda declarado como código Terraform.
- [ ] `terraform plan`/`apply` reproduce el entorno desplegado de forma verificable.

## Alcance
Nuevo directorio de infraestructura como código (a definir su ubicación exacta al
implementar), sobre el proveedor cloud elegido en EPIC-8.

## Fuera de alcance
Multi-entorno (dev/staging/prod separados), salvo que se pida después.

## Nota
Requiere decisión previa del usuario sobre la herramienta de IaC (se asume Terraform por
indicación ya dada, pero cualquier detalle de proveedor/módulos queda pendiente hasta
EPIC-8) antes de poder implementarse — ver Shepard/Liara cuando toque.

## Estado
Propuesta
