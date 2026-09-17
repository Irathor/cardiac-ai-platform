# EPIC-8: Deployment cloud

## Historia de usuario
Como equipo, quiero desplegar el stack real en Oracle Cloud (Always Free), para que el
proyecto sea accesible como demo real, con HTTPS, más allá de un `docker compose up` local.

## Tipo
Normal

## Bloqueada por
EPIC-9 (Infrastructure as Code con Terraform) — el despliegue real de esta Epic se levanta
mediante el Terraform de `infrastructure/terraform/oracle/` (provisión de la instancia +
cloud-init que arranca el stack); no hay nada que verificar en EPIC-8 hasta que exista esa
infraestructura.

## Criterios de aceptación
- [ ] El stack completo (`docker-compose.yml` del repo, sin fork paralelo) corre en una
      Oracle Compute Instance `VM.Standard.A1.Flex` (ARM Ampere, Always Free — hasta 4
      OCPU/24GB), provisionada por el Terraform de EPIC-9. **Pendiente**: requiere
      `terraform apply` real, que a su vez requiere que el usuario aporte sus credenciales
      de Oracle Cloud (ver `infrastructure/terraform/oracle/README.md`) — el código está
      listo y verificado (`terraform validate` limpio), no aplicado todavía.
- [x] Las imágenes `backend` y `frontend` publicadas en GHCR (job `build-and-push` de
      `.github/workflows/ci.yml`) incluyen variante `linux/arm64` además de `linux/amd64`
      (build multi-plataforma vía `docker buildx` + `docker/setup-qemu-action@v3`). El resto
      de imágenes del stack ya publican manifiestos multi-arquitectura de forma nativa —
      confirmado contra sus repositorios oficiales, no requieren cambio.
- [x] Solo los puertos 80 y 443 están expuestos a Internet en el diseño de red (Oracle
      Security List, verificado por lectura directa de `infrastructure/terraform/oracle/main.tf`
      y por `security-review`). `postgres`, `redis`, `minio`, `mlflow`, `prometheus` y
      `grafana` permanecen accesibles solo en `127.0.0.1` de la instancia. **La verificación
      real contra una instancia desplegada queda pendiente** hasta el `terraform apply`.
- [x] Reverse proxy **Caddy** (`docker-compose.yml`, `infrastructure/caddy/Caddyfile`)
      escucha en 80/443 delante de `frontend` y `backend` (rutas `/api/*`), con HTTPS
      automático vía Let's Encrypt — `Caddyfile` validado con el binario real
      (`caddy validate --adapter caddyfile`: "Valid configuration"). Hostname:
      `<ip-publica>.sslip.io`, confirmado por el usuario (sin dominio propio).
- [x] Los secretos llegan a la instancia vía el `.env` que el cloud-init de Terraform
      escribe en el primer arranque, a partir de variables `sensitive` de un
      `terraform.tfvars` no versionado — nunca comiteados al repo. **Hallazgo real de
      `security-review` corregido en este checkpoint**: el heredoc que escribe `.env` no
      tenía el delimitador entre comillas, lo que permitía que un valor de secreto con
      `$(...)` se ejecutara como comando de shell (como root) en el primer arranque —
      arreglado y verificado funcionalmente con un caso malicioso simulado (ver
      "Verificación" abajo).
- [ ] El despliegue es verificable de forma real y remota (`curl .../health/ready` contra la
      instancia real, frontend cargando sobre HTTPS desde un navegador externo). **Pendiente
      del `terraform apply` real** — no se puede verificar sin la instancia desplegada.
- [x] Ejecutado el skill `security-review` (orquestador) sobre la configuración de red/
      secretos/Caddy: 1 hallazgo real MEDIUM (inyección de comandos vía heredoc sin comillas
      en cloud-init), corregido en este mismo checkpoint; el resto evaluado sin hallazgos
      bloqueantes (secretos vía `user_data`/IMDS anotado como fast-follow razonable en
      `docs/BACKLOG.md`, no bloqueante en el contexto de una instancia personal de un solo
      operador).

## Alcance
- `infrastructure/caddy/Caddyfile` y el servicio `caddy` nuevo en `docker-compose.yml`.
- Ajuste de puertos publicados en `docker-compose.yml` si hiciera falta (frontend/backend
  dejan de publicarse directamente si Caddy pasa a ser el único punto de entrada externo;
  el resto de servicios ya estaba en `127.0.0.1` y no cambia).
- `.github/workflows/ci.yml`, job `build-and-push`: build multi-plataforma
  (`linux/amd64,linux/arm64`) vía `docker buildx` para `backend` y `frontend`.
- Verificación real contra la instancia Oracle provisionada en EPIC-9 (Garrus).

## Fuera de alcance
- Desplegar AWS de verdad (`terraform apply` sobre `infrastructure/terraform/aws/`) — el
  scaffold de EPIC-9 se prepara pero no se aplica; queda para cuando el usuario decida
  pagarlo.
- Observabilidad real más allá de los health checks (trazas, agregación de logs, alertas de
  error), gestión de secretos con vault/secret manager del proveedor, política de
  versionado de API, seguimiento de coste/uso del LLM — quedan en `docs/BACKLOG.md`, se
  activan aparte según "Antes de un despliegue de producción real" en las convenciones del
  equipo. (HTTPS forzado, que es otra de esas cinco comprobaciones, **sí** entra en el
  alcance de esta Epic porque el despliegue real ya está lo bastante cerca como para
  justificarlo — ver criterios de aceptación arriba.)
- Multi-entorno (dev/staging/prod separados en Oracle) — ver EPIC-9.
- Alta disponibilidad / múltiples instancias / balanceo de carga — una sola Compute
  Instance Always Free es el alcance deliberado de esta Epic.

## Decisiones confirmadas
Añadir Caddy es una pieza de infraestructura nueva y persistente que antes no existía en
`docker-compose.yml` (ver "Regla de autonomía" en las convenciones del equipo: cuenta como
decisión grande). El usuario ha confirmado explícitamente ambas decisiones antes de
implementar, sin ambigüedad pendiente: Caddy con HTTPS automático vía Let's Encrypt como
reverse proxy único de entrada, y `<ip-publica>.sslip.io` como hostname público — sin
dominio propio, coste cero. Ver ADR-6 (Oracle Cloud real + AWS scaffold) para el contexto
completo de la decisión de proveedor que motiva este despliegue.

## Verificación (parcial — checkpoint intermedio, no cierre)
- `docker compose config -q` con Caddy incluido: sintaxis válida (re-verificado de forma
  independiente por el orquestador).
- `Caddyfile` validado con el binario real (`caddy:2.10-alpine`, `caddy validate`): válido.
- `security-review`: 1 hallazgo real MEDIUM (heredoc de cloud-init sin comillas, inyección
  de comandos vía valores de secreto) — corregido y verificado funcionalmente (caso
  malicioso simulado, confirmado que el payload queda escrito literalmente, nunca se
  ejecuta). Resto sin hallazgos bloqueantes.
- Pendiente para cerrar de verdad: `terraform apply` real contra Oracle Cloud (requiere
  credenciales del usuario), y la verificación remota real (`curl`/navegador externo) contra
  la instancia ya desplegada.

## Estado
En progreso
