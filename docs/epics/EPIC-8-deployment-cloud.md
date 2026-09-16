# EPIC-8: Deployment cloud

## Historia de usuario
Como equipo, quiero desplegar el stack real en un proveedor cloud, para que el proyecto sea
accesible como demo real más allá de un `docker compose up` local.

## Tipo
Normal

## Bloqueada por
EPIC-5 (CI/CD ampliado — escaneo de dependencias + build/push de imágenes).

## Criterios de aceptación
- [ ] El stack se despliega realmente en el proveedor cloud que se decida.
- [ ] El despliegue es accesible y verificable (health checks reales contra el entorno
      desplegado, no solo local).

## Alcance
A definir junto con el proveedor cloud elegido.

## Fuera de alcance
HTTPS forzado/observabilidad real/gestión de secretos avanzada — quedan en
`docs/BACKLOG.md`, se activan aparte antes de un despliegue de producción real (ver
"Antes de un despliegue de producción real" en las convenciones del equipo).

## Nota
Requiere decisión previa del usuario sobre el proveedor cloud antes de poder implementarse —
ver Shepard/Liara cuando toque.

## Estado
Propuesta
