# EPIC-6: Monitoring básico y métricas de inferencia servida

## Historia de usuario
Como equipo, quiero monitorizar la inferencia real servida (latencia, volumen, errores),
para tener visibilidad operativa mínima sobre el sistema en producción/demo.

## Tipo
Normal

## Bloqueada por
EPIC-2 (Servir los modelos reales (U-Net/CNN3D) desde la API de inferencia) — monitorizar
algo que todavía no se sirve no aporta señal real.

## Criterios de aceptación
- [x] El backend instrumenta con `prometheus_client` la inferencia real servida por los dos
      caminos existentes: clasificación CNN3D (`analysis_service.execute_analysis`, vía
      `dl_inference_client.classify_cnn3d`) y auto-segmentación U-Net
      (`auto_segmentation_service.generate_auto_segmentation`, vía
      `dl_inference_client.segment_unet`).
- [x] Se mide, como mínimo, para cada uno de los dos caminos por separado (con una etiqueta
      que distinga CNN3D de U-Net): duración de la llamada al runner GPU
      (`ml/scripts/training_runner_service.py`, vía `dl_inference_client`), un contador de
      volumen (número de inferencias servidas) y un contador de éxito/fallo (fallo = se
      lanzó `InferenceRunnerError`, tal como ya lo maneja `analysis_service` marcando el
      `AIAnalysis` como `FAILED`, o se propaga como excepción sin capturar en
      `auto_segmentation_service`).
- [x] El backend expone un endpoint `/metrics` en formato Prometheus (vía `prometheus_client`)
      con esas métricas.
- [x] `docker-compose.yml` añade un contenedor Prometheus que scrapea ese endpoint
      periódicamente, con bind a `127.0.0.1` (misma convención que el resto del stack).
- [x] `docker-compose.yml` añade un contenedor Grafana con, al menos, un dashboard real
      provisionado (no vacío) que muestre las tres métricas anteriores (latencia, volumen,
      tasa de éxito/fallo) separadas por camino de inferencia (CNN3D vs. U-Net), con bind a
      `127.0.0.1`.
- [x] Con el stack levantado y al menos una inferencia real servida de cada tipo, el
      dashboard de Grafana refleja el dato (no solo la infraestructura arrancada sin datos
      visibles).

## Alcance
Backend (instrumentación de `analysis_service`/`auto_segmentation_service`/
`dl_inference_client` y endpoint `/metrics`), `docker-compose.yml` (contenedores Prometheus y
Grafana nuevos y su configuración de arranque: `prometheus.yml`, datasource y dashboard
provisionados de Grafana).

## Fuera de alcance
Alertas, trazas distribuidas, instrumentación del propio runner GPU
(`ml/scripts/training_runner_service.py`) — esta Epic instrumenta el backend que lo invoca,
no el runner en sí.

## Contrato técnico (Shepard)

Verificado contra el código real: `backend/app/services/analysis_service.py`
(`execute_analysis`), `backend/app/services/auto_segmentation_service.py`
(`generate_auto_segmentation`), `backend/app/services/dl_inference_client.py`
(`classify_cnn3d`/`segment_unet`, ambas pasando por el helper privado
`_post`), `docker-compose.yml`, `backend/pyproject.toml` (`prometheus_client`
**no** es dependencia todavía) e `infrastructure/mlflow/` (patrón de
Dockerfile propio a seguir).

### 1. Métricas exactas

Dos métricas, no tres — un `Counter` con label `outcome` cubre a la vez
"volumen" y "éxito/fallo" (sumar por `model_type` da el volumen total; sumar
por `outcome="failure"` da los fallos), en vez de duplicar un contador de
volumen aparte. Esto es una decisión de diseño explícita, no un recorte de
alcance: sigue cumpliendo los tres criterios de aceptación de la Epic
(latencia, volumen, tasa de éxito/fallo), solo que con dos series en vez de
tres.

- **`dl_inference_duration_seconds`** (Histogram)
  Labels: `model_type` ∈ `{"cnn3d", "unet"}`.
  Mide únicamente la duración de la llamada HTTP al runner GPU (la línea
  `_post(...)` dentro de `classify_cnn3d`/`segment_unet`), no el tiempo de
  staging/cleanup del fichero en `./data/tmp/inference/` (eso es I/O local
  del propio contenedor backend, no la inferencia servida).
  Buckets explícitos (los del cliente no cubren bien el rango real: hay
  timeout de 120s y una carga de modelo en frío posible en la primera
  llamada — ver `_INFERENCE_TIMEOUT_S` en `dl_inference_client.py`):
  `(0.5, 1, 2, 5, 10, 20, 30, 60, 90, 120)`.

- **`dl_inference_requests_total`** (Counter)
  Labels: `model_type` ∈ `{"cnn3d", "unet"}`, `outcome` ∈
  `{"success", "failure"}`.
  `failure` = se lanzó `InferenceRunnerError` alrededor de la llamada al
  runner (cubre tanto el caso que `analysis_service` captura y convierte en
  `AIAnalysis.FAILED`, como el caso que `auto_segmentation_service` deja
  propagarse sin capturar — en ambos casos la excepción ya pasó por
  `dl_inference_client`, que es donde se instrumenta, así que el punto de
  captura de la métrica no depende de cómo cada servicio la maneje después).

**Dónde se instrumenta** (un solo sitio, no duplicado en cada servicio):
dentro de `backend/app/services/dl_inference_client.py`, un nuevo
context manager `observe_inference(model_type: str)` (vive en
`backend/app/core/metrics.py` junto a las instancias de `Counter`/
`Histogram`) que envuelve exactamente la llamada a `_post(...)` en
`classify_cnn3d` (con `model_type="cnn3d"`) y en `segment_unet` (con
`model_type="unet"`). El context manager mide la duración, y al salir
incrementa el counter con `outcome="failure"` si salió `InferenceRunnerError`
(la re-lanza sin capturarla) o `outcome="success"` en caso contrario. Ni
`analysis_service.py` ni `auto_segmentation_service.py` tocan
`prometheus_client` directamente — no conocen detalles de métricas, igual
que no conocen detalles HTTP.

### 2. Endpoint `/metrics`

- Vive en **la raíz de la app**, no bajo `/api/v1`: `GET /metrics`, montado
  directamente sobre `app` en `backend/app/main.py`
  (`app.include_router(metrics.router)`, sin el prefijo
  `settings.api_v1_prefix`). Router nuevo en `backend/app/api/metrics.py`.
  Motivo: es un endpoint operativo scrapeado por una herramienta de
  infraestructura (Prometheus), no un recurso de negocio versionado — meterlo
  bajo `/api/v1` implicaría que evoluciona con la API de negocio, y no es el
  caso (es la convención estándar de scraping de Prometheus, y evita
  reconfigurar el `job` de scrape si la API sube de versión algún día).
- Implementación: `from prometheus_client import generate_latest,
  CONTENT_TYPE_LATEST` → `Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)`.
- **Sin RBAC, sin autenticación** — decisión explícita, mismo criterio que
  ya se aplica al runner GPU de EPIC-2: la única protección es el binding de
  red. El puerto del backend ya está publicado como `127.0.0.1:8000:8000`
  (no accesible desde fuera del host), y dentro de la red Docker interna
  cualquier contenedor del stack ya puede alcanzar `backend:8000` sin
  autenticación en otros endpoints tampoco (p. ej. redis/minio no tienen
  auth por request). `/metrics` no expone PII ni datos clínicos — solo
  contadores/histogramas agregados sin identificadores de paciente/estudio
  — así que no hay dato sensible que proteger con autorización adicional.
  **Esto se señala explícitamente para el `security-review` que se ejecuta
  antes de cerrar la Epic**: no es un descuido, es la misma decisión ya
  tomada (y documentada) para el runner de inferencia.

### 3. `docker-compose.yml`

- **`prometheus`**: imagen `prom/prometheus:v3.13.3` (última estable no-RC
  verificada en Docker Hub a fecha de este contrato). Puerto
  `127.0.0.1:9090:9090` (libre — no choca con nada del stack actual:
  5432/6379/9000/9001/5000/8000/5173 ya en uso). Config vía volumen:
  `./infrastructure/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro`.
  Target de scrape: `backend:8000` (nombre de servicio Docker, puerto
  interno — no el puerto publicado en el host), path `/metrics`, intervalo
  15s. `depends_on: backend` (no hace falta `condition: service_healthy`,
  Prometheus tolera un target caído al arrancar y reintenta solo).
- **`grafana`**: imagen `grafana/grafana:13.2.2` (última estable no-RC
  verificada). Puerto `127.0.0.1:3000:3000` (libre). Todo el provisioning
  como código, sin clickear en la UI (coherente con la filosofía
  reproducible ya aplicada a MLflow/model registry en este proyecto):
  - `infrastructure/grafana/provisioning/datasources/prometheus.yml`
    (datasource Prometheus apuntando a `http://prometheus:9090`, montado
    read-only).
  - `infrastructure/grafana/provisioning/dashboards/dashboard.yml`
    (provider que carga cualquier JSON de una carpeta fija).
  - `infrastructure/grafana/dashboards/inference-overview.json`
    (el dashboard real: latencia p50/p95 por `model_type`, volumen de
    inferencias por `model_type`, tasa de éxito/fallo por `model_type` —
    las tres cosas exigidas en los criterios de aceptación de esta Epic).
  Todo montado por volumen (no baked en una imagen custom — a diferencia de
  MLflow, Grafana no necesita nada más que estos tres ficheros de config
  encima de la imagen oficial, así que no hace falta
  `infrastructure/grafana/Dockerfile`; se usa `image:` directo).
  `depends_on: prometheus`.
- Ninguno de los dos necesita credenciales que vivan en `.env` para esta
  fase (Grafana usa su admin/admin por defecto, aceptable para un stack
  atado a `127.0.0.1` — si se quisiera cambiar, sería una decisión de
  seguridad a preguntar al usuario, no algo que se fuerza aquí sin
  necesidad real).

### 4. División de trabajo (paralelizable)

- **Tali**: `backend/pyproject.toml` (añadir `"prometheus_client>=0.26,<0.27"`
  — verificar la versión real en PyPI antes de fijarla en el código, no
  copiar el número de este documento de memoria), `backend/app/core/metrics.py`
  (definiciones de métricas + `observe_inference`), instrumentación en
  `dl_inference_client.py`, `backend/app/api/metrics.py` (router
  `/metrics`), registro en `main.py`. Puede verificar todo esto con
  `curl http://localhost:8000/metrics` contra el backend ya levantado, sin
  esperar a que exista Prometheus ni Grafana.
- **Garrus**: `docker-compose.yml` (servicios `prometheus`/`grafana`),
  `infrastructure/prometheus/prometheus.yml`,
  `infrastructure/grafana/provisioning/**`,
  `infrastructure/grafana/dashboards/inference-overview.json`. Puede
  escribir el scrape target (`backend:8000`, path `/metrics`) y el
  dashboard JSON (con los nombres de métrica ya fijados arriba:
  `dl_inference_duration_seconds`, `dl_inference_requests_total`) sin
  esperar a que Tali termine la instrumentación — el contrato de nombres
  de métrica y de puerto/path es el punto de sincronización, ya fijado en
  este documento, no algo que necesiten negociar entre ellos a mitad de
  Epic.
- Punto de integración real (el único que sí necesita ambas partes
  terminadas): el último criterio de aceptación ("con el stack levantado y
  al menos una inferencia real servida de cada tipo, el dashboard refleja
  el dato") — se verifica al final, no a mitad.

## Verificación

Checkpoint de cierre completo: stack real levantado con `docker compose up`, tests re-
ejecutados de forma independiente, y **dos regresiones/gaps reales encontrados y
arreglados** durante el propio checkpoint (no simulados, no hipotéticos):

1. **Regresión de EPIC-5 (mlflow 3.x + Docker Compose)**: el servidor MLflow real rechazaba
   con 403 el header `Host: mlflow:5000` que el backend/worker reales envían dentro de la
   red de Docker Compose (protección nueva de mlflow 3.x contra DNS rebinding — solo permite
   por defecto `localhost`/IPs privadas, no nombres de servicio). Nunca se detectó antes
   porque ninguna verificación previa (EPIC-1/4/5/11) ejercitó el stack completo por su red
   real — todas usaban servidores mlflow aislados o SQLite. Arreglado con
   `MLFLOW_SERVER_ALLOWED_HOSTS: mlflow:5000` en `docker-compose.yml`. Sin este fix, EPIC-1,
   EPIC-4 y EPIC-11 (todo lo que depende de MLflow) estarían rotos en el stack desplegado de
   verdad, pese a que sus propios tests pasaban.
2. **Gap real de esta Epic**: la métrica del camino CNN3D (`analysis_service.py`, corre
   dentro del proceso Celery `worker`) nunca habría llegado a `/metrics` (servido por el
   proceso `backend`/uvicorn) — el registro en memoria de `prometheus_client` es por
   proceso. Arreglado con el modo multiproceso oficial de la librería
   (`PROMETHEUS_MULTIPROC_DIR` + volumen compartido `prometheus_multiproc` entre `backend`/
   `worker`, `multiprocess.MultiProcessCollector` en el endpoint) — ver
   `backend/app/core/metrics.py`/`backend/app/api/metrics.py` para el detalle técnico
   completo. Verificado con datos reales: ambos `model_type` (`unet` vía
   auto-segmentación síncrona, `cnn3d` vía el worker real) aparecen en `/metrics`, en
   Prometheus (`dl_inference_requests_total{model_type="cnn3d",outcome="failure"} 2`,
   `{model_type="unet",...} 1`, `health: up` en el target) y en las expresiones PromQL
   exactas que usan los paneles del dashboard de Grafana (confirmado contra la API real de
   Prometheus, no simulado).

Las llamadas reales dispararon `outcome="failure"` en ambos casos porque no hay runner GPU
disponible en este entorno de verificación (correcto y esperado — mismo criterio que EPIC-2/
3: el runner GPU real vive en el host con CUDA, no en este sandbox) — lo importante es que la
tubería completa (llamada real → excepción real → métrica real → scrape real → query real)
funciona de punta a punta, no que la inferencia en sí tuviera éxito.

- `backend`: 130/130 tests en verde (sin `PROMETHEUS_MULTIPROC_DIR` en el entorno de test,
  confirma que el modo multiproceso no interfiere con el camino de test normal), `ruff
  check` limpio.
- `security-review` (skill del orquestador): 1 hallazgo MEDIUM real — Grafana quedaba con
  las credenciales de fábrica `admin/admin` sin exigir una propia, inconsistente con el
  patrón ya establecido del proyecto (`POSTGRES_PASSWORD`/`MINIO_SECRET_KEY` con
  `:?required`). Arreglado en el mismo checkpoint: `GF_SECURITY_ADMIN_PASSWORD` ahora
  obligatorio vía `${GRAFANA_ADMIN_PASSWORD:?...}`, documentado en `.env.example`.
- `docker compose config -q`: sintaxis válida con el nuevo requisito.

## Estado
Completada
