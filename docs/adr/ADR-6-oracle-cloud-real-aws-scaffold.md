# ADR-6: Oracle Cloud como despliegue real, AWS como scaffold preparado

## Estado
Aceptada

## Contexto
El proyecto necesita un despliegue cloud real y accesible como demo, gratuito de forma
indefinida (no solo durante un periodo de prueba). El stack completo del repo —
Postgres + Redis + MinIO + MLflow + backend + worker + frontend + Prometheus + Grafana —
no cabe con RAM suficiente en ningún free tier salvo el de Oracle Cloud Always Free, que
ofrece hasta 4 OCPU / 24 GB de RAM de forma gratuita e indefinida en instancias ARM Ampere
(`VM.Standard.A1.Flex`). Se valoró AWS como alternativa: su free tier (12 meses, instancias
`t2.micro`/`t3.micro` con 1 GB de RAM) no cubre esta carga sin incurrir en coste. Aun así, el
usuario quiere tener AWS preparado como Terraform listo para aplicar el día que decida
pagarlo — es un proveedor más reconocido en un CV/portfolio que Oracle Cloud, y quiere esa
opción disponible sin tener que diseñarla desde cero más adelante.

## Decisión
Se despliega el stack real sobre Oracle Cloud (instancia `VM.Standard.A1.Flex`, ARM Ampere,
Always Free), provisionada y aplicada de verdad vía Terraform en
`infrastructure/terraform/oracle/` (EPIC-9, verificado con `terraform apply` real y
`terraform plan` sin diff posterior).

AWS se prepara como un root module de Terraform independiente en
`infrastructure/terraform/aws/`, con la misma composición de archivos y convención de
nombres de variables/outputs que `oracle/`, pero **nunca se aplica** como parte de este
trabajo: solo se valida (`terraform validate`) en CI/local, sin credenciales de AWS en
ningún sitio del repo. Queda listo para que el usuario ejecute `terraform apply` cuando
decida asumir el coste.

No se fuerza un módulo Terraform "compartido" entre ambos proveedores (red, cómputo, etc.):
OCI y AWS usan tipos de recurso de Terraform completamente distintos (proveedores `oci` y
`aws`, sin superposición real de esquema). Una abstracción común ahí desplazaría la
complejidad de un sitio a otro sin reducirla — cada proveedor es un root module
autocontenido, comparable con el otro solo por convención de nombres, no por código
compartido.

## Consecuencias

**Ventajas**
- Despliegue real, gratuito de forma indefinida, sin trampa de "prueba de 12 meses".
- AWS queda listo para activar sin trabajo de diseño adicional cuando el usuario decida
  pagarlo — solo rellenar `terraform.tfvars` con credenciales/región/tamaño reales.
- Cada root module es legible de forma aislada; no hay que entender una capa de abstracción
  extra para saber qué provisiona cada proveedor.

**Desventajas / deuda técnica asumida**
- Al ser ARM (Ampere), las imágenes Docker publicadas desde CI deben ser multi-arquitectura.
  El job `build-and-push` de `.github/workflows/ci.yml` (introducido en EPIC-5) gana
  `docker buildx` para publicar `backend` y `frontend` en `linux/amd64` + `linux/arm64`; el
  resto de imágenes del stack ya publica manifiestos multi-arquitectura de forma nativa, sin
  cambios necesarios.
- Se introduce Caddy como pieza de infraestructura nueva y persistente en
  `docker-compose.yml` (antes no existía) para servir HTTPS real delante de frontend y
  backend — aprobado explícitamente por el usuario junto con `sslip.io` como hostname
  público (sin dominio propio, coste cero), en vez de nginx+certbot manual.
- El estado de Terraform de Oracle vive en local (`terraform.tfstate*` en `.gitignore`) por
  ahora — decisión adecuada a la escala actual (un solo operador, sin equipo concurrente
  tocando la infraestructura), documentada como deuda técnica migrable a un backend remoto
  (p. ej. OCI Object Storage, compatible S3) si en el futuro hace falta colaboración
  concurrente sobre el mismo estado.
- El scaffold de AWS, al no aplicarse nunca, no tiene verificación real de que
  `terraform apply` funcione de punta a punta sobre una cuenta AWS real — solo
  `terraform validate` da garantía de sintaxis/tipos, no de que el plan sea aplicable sin
  fricción el día que se active.
