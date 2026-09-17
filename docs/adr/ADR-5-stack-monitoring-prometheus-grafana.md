# ADR-5: Stack de monitoring: Prometheus + Grafana

## Estado
Aceptada

## Contexto
[EPIC-6 (Monitoring básico y métricas de inferencia servida)](../epics/EPIC-6-monitoring-basico.md)
quedó bloqueada por una decisión pendiente: el proyecto sirve inferencia real
(EPIC-2/EPIC-3) por dos caminos — clasificación CNN3D (`analysis_service.execute_analysis`,
vía `dl_inference_client.classify_cnn3d`) y auto-segmentación U-Net
(`auto_segmentation_service.generate_auto_segmentation`, vía `dl_inference_client.segment_unet`)
— ambos delegando la inferencia pesada al runner GPU
(`ml/scripts/training_runner_service.py`) sobre HTTP, con la posibilidad real de fallo
(`InferenceRunnerError` cuando el runner no responde, devuelve un status distinto de 200, o
excede el timeout configurado). No había visibilidad operativa alguna sobre la latencia, el
volumen ni la tasa de fallo de esa inferencia servida.

Se valoraron dos opciones:

1. **Endpoint `/metrics` propio minimalista**: el backend expone un endpoint con las métricas
   ya agregadas en memoria (contadores/latencias simples), sin infraestructura nueva que
   desplegar ni mantener. Suficiente para inspección puntual, pero sin histórico, sin
   dashboards ni capacidad de consulta/alerta real.
2. **Prometheus + Grafana**: el backend expone igualmente un endpoint `/metrics` en formato
   Prometheus (usando la librería estándar `prometheus_client` de Python — esto no cambia
   entre las dos opciones, ambas necesitan instrumentar el código con contadores/histogramas;
   la diferencia es quién consume ese endpoint y con qué capacidad de consulta), pero además
   se añaden dos contenedores nuevos y persistentes al stack: Prometheus (scrapea el
   endpoint periódicamente y guarda la serie temporal) y Grafana (dashboards reales sobre esa
   serie temporal).

Se preguntó al usuario explícitamente por tratarse de una decisión grande (nueva
infraestructura persistente en el stack, ver "Regla de autonomía" en
`~/.claude/CLAUDE.md`).

## Decisión
Se adopta **Prometheus + Grafana**, elegido explícitamente por el usuario sobre la
alternativa del endpoint `/metrics` propio minimalista.

El backend sigue exponiendo un endpoint `/metrics` en formato Prometheus mediante
`prometheus_client` — eso no varía entre las dos opciones valoradas. Lo que cambia es que
ahora es un contenedor Prometheus (nuevo en `docker-compose.yml`) quien scrapea ese endpoint
en vez de que nadie lo consuma, y un contenedor Grafana (también nuevo) quien visualiza esa
serie temporal en dashboards reales.

Ambos contenedores siguen la convención ya establecida en `docker-compose.yml` para el resto
de servicios del stack (postgres, redis, minio, mlflow, backend, frontend): puertos publicados
únicamente con bind a `127.0.0.1` (p. ej. `127.0.0.1:9090:9090` para Prometheus,
`127.0.0.1:3000:3000` para Grafana), no expuestos a la red externa.

## Consecuencias
- **Ventajas**: histórico real de métricas (no solo un snapshot en memoria), dashboards
  visuales concretos sobre la inferencia servida (latencia, volumen, tasa de éxito/fallo de
  CNN3D y de auto-segmentación U-Net), capacidad de consulta ad-hoc (PromQL) y base para
  alertas futuras si el proyecto las necesita más adelante. Valor añadido real para un
  portfolio de MLOps, que es explícitamente el motivo por el que el usuario prefirió esta
  opción sobre la minimalista.
- **Desventajas / deuda técnica asumida**: dos contenedores nuevos y persistentes que
  mantener, actualizar y asegurar (siguen el mismo binding a `127.0.0.1` que el resto del
  stack, así que no amplían la superficie expuesta a la red externa, pero sí la superficie
  interna a documentar/operar) — más complejidad de despliegue que la alternativa
  minimalista descartada. Los dashboards de Grafana y las reglas de scrape de Prometheus son
  configuración nueva que vive en el repo y hay que mantener sincronizada con lo que el
  backend instrumenta.
- **Impacto en otros módulos**: el backend (Tali) añade instrumentación real con
  `prometheus_client` en los puntos de inferencia servida (`analysis_service`,
  `auto_segmentation_service`, vía `dl_inference_client`). Garrus añade los dos contenedores
  nuevos a `docker-compose.yml` y su configuración de arranque (`prometheus.yml` con el
  target del backend, datasource y dashboard provisionados en Grafana). No afecta a EDI ni al
  runner GPU directamente — el runner no se instrumenta en esta fase, solo el backend que lo
  invoca (ver criterios de aceptación de EPIC-6 para el detalle exacto de qué se mide).
- Con esta decisión tomada, [EPIC-6](../epics/EPIC-6-monitoring-basico.md) deja de estar en
  la sección "Niebla" de `docs/BACKLOG.md` y queda lista para implementarse.
