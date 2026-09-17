# EPIC-7: Detección de drift sobre biomarcadores/predicciones

## Historia de usuario
Como ingeniero de ML/MLOps, quiero detectar cuándo la distribución de biomarcadores o
predicciones recientes se desvía del dataset de entrenamiento base, para poder anticipar
degradación del modelo en producción.

## Tipo
Normal (decisión del usuario: mecanismo estadístico propio con `scipy`/`numpy`, no una
librería de ML como Evidently — comparar dos distribuciones con un test estadístico estándar
es lógica determinista sobre datos ya existentes, no requiere entrenar ni generalizar nada
nuevo).

## Bloqueada por
EPIC-6 (Monitoring básico y métricas de inferencia servida) — esta Epic reutiliza el stack
Prometheus/Grafana y el endpoint `/metrics` que EPIC-6 ya dejó levantado.

## Criterios de aceptación
- [x] Se implementa un cálculo de drift (invocable bajo demanda vía el endpoint de abajo, sin
      necesidad de un job periódico nuevo en esta fase) que compara, para el `ModelVersion` en
      estado `PRODUCTION` actual, dos tipos de deriva:
  1. **Deriva de biomarcadores** (numérica continua): por cada `name` distinto presente en
     `BiomarkerMeasurement` (LVEF, volúmenes, etc.), test de Kolmogorov-Smirnov de dos muestras
     (`scipy.stats.ks_2samp`) entre los valores **recientes** (ventana móvil configurable, por
     defecto las últimas 100 mediciones o los últimos 30 días, lo que ocurra primero) y los
     valores **base**: mediciones de `BiomarkerMeasurement` calculadas sobre `Segmentation` de
     casos pertenecientes al `DatasetVersion` (LOCKED) que entrenó el `TrainingRun`/
     `ModelVersion` actualmente en `PRODUCTION` (vía `DatasetCase.patient_id`/`annotation_id`
     → estudio → serie → segmentación; si un biomarcador no tiene suficientes mediciones base o
     recientes, ese `name` se omite del resultado con un motivo explícito, no se fuerza un
     resultado sin significancia estadística).
  2. **Deriva de predicciones** (categórica): Population Stability Index (PSI) entre la
     distribución de `AIAnalysis.predicted_class` (solo análisis `status="COMPLETED"`) en la
     misma ventana reciente que arriba, y una distribución **base** fijada una vez: las primeras
     100 predicciones (o los primeros 30 días) servidas por ese `ModelVersion` tras su promoción
     a `PRODUCTION`. No se compara contra las etiquetas ground-truth del dataset de
     entrenamiento porque eso mediría desplazamiento de las etiquetas, no del comportamiento del
     modelo — la comparación correcta para "predicciones recientes vs. base" es predicción
     contra predicción.
- [x] Cada resultado (por biomarcador, y el de predicción) incluye el estadístico (KS statistic
      + p-value, o valor de PSI), el tamaño de cada muestra, y si supera un umbral configurable
      que marca "drift detectado" (por defecto: `p < 0.05` para KS; `PSI > 0.2` para deriva
      significativa, `0.1 ≤ PSI ≤ 0.2` para deriva moderada — convención estándar de la
      industria para PSI).
- [x] El resultado se expone por **dos vías**, reutilizando patrones ya existentes en el
      proyecto en vez de inventar uno nuevo:
  1. Endpoint de solo lectura `GET /api/v1/model-versions/{model_version_id}/drift` (mismo
     patrón de RBAC de solo-lectura que `GET /api/v1/model-versions/registry-divergence` de
     EPIC-4), con el detalle completo (estadístico, p-value/PSI, tamaños de muestra, umbral,
     flag de drift) por biomarcador y para la predicción.
  2. Gauges nuevos en el `/metrics` ya existente (EPIC-6): `biomarker_drift_ks_statistic` y
     `biomarker_drift_pvalue` (label `biomarker_name`), `prediction_drift_psi` — todos
     etiquetados con el `model_version_id` en `PRODUCTION` evaluado, para que el dashboard de
     Grafana de EPIC-6 pueda añadir un panel de deriva sin montar infraestructura nueva.
- [x] Con datos de prueba donde se fuerza un desplazamiento deliberado en la ventana reciente
      (para al menos un biomarcador y para la distribución de clases predichas), el resultado
      marca "drift detectado"; con datos sin desplazamiento deliberado, no lo marca (verifica
      que el test no dispara falsos positivos con datos equivalentes).
- [x] No dispara ninguna acción automática (alerta, reentrenamiento) — solo expone el resultado
      para inspección humana. El disparo automático de reentrenamiento queda fuera de esta Epic
      (ver "Fuera de alcance").

## Alcance
Backend (`backend/app/services/`, nuevo servicio de cálculo de drift; `backend/app/api/v1/`,
nuevo endpoint; `backend/app/core/metrics.py`/`backend/app/api/metrics.py`, gauges nuevos).
`scipy`/`numpy` ya son dependencia transitiva del backend a través del paquete `ml`
(`cardiac_ai_ml`, ya importado desde varios servicios) — no se añade ninguna dependencia nueva
a `backend/pyproject.toml`.

## Fuera de alcance
Reentrenamiento automático disparado por drift (queda como dirección en "Niebla" de
`docs/BACKLOG.md`, sin forma concreta todavía). Alertas (Alertmanager u otro mecanismo de
notificación) sobre el drift detectado — esta Epic solo expone el dato, no dispara nada.

## Contrato técnico (Shepard)

Epic de un único servicio (backend, Tali) — no toca `docker-compose.yml` ni
Prometheus/Grafana como infraestructura nueva (ambos ya existen desde
EPIC-6), así que **no hace falta a Garrus**. La única pieza no-obvia es que
los gauges nuevos viven en un proceso que corre en *multiprocess mode*
(ver punto 5) — eso lo resuelve el propio `prometheus_client`, no requiere
tocar `docker-compose.yml`.

### 1. Dataset base de biomarcadores — query real

Reutiliza exactamente el mismo camino que ya usa el entrenamiento
(`app.services.training_service._cases_for_split` /
`app.repositories.annotation_repository.get_imaging_study`) para no crear
una segunda fuente de verdad sobre "cómo se llega de un `DatasetCase` a sus
datos": si training cambia esa lógica, drift la hereda automáticamente sin
tocar código de drift.

Para el `ModelVersion` en `PRODUCTION` evaluado:
1. `training_run = model_version.training_run` (relationship ya existe).
2. Si `training_run.dataset_version_id is None` (modelo `UNET_SEGMENTATION`
   o `CNN3D_CLASSIFICATION` — no consumen `DatasetVersion`, ver
   `TrainingRun.__doc__`): **toda la sección de biomarcadores se omite**
   con `biomarkers_skipped_reason="production model type <model_type> was
   not trained against a DatasetVersion"` — solo se calcula deriva de
   predicción (punto 6 más abajo trata el umbral). Esto no estaba explícito
   en la Epic original; lo dejo fijado aquí porque de lo contrario el
   endpoint fallaría sin motivo claro sobre exactamente 2 de los 3 tipos de
   modelo del proyecto.
3. Si hay `dataset_version_id`, para cada `DatasetCase` en
   `dataset_repository.list_cases(db, dataset_version_id)` (**todas las
   splits** TRAIN+VALIDATION+TEST — deriva mide la población total sobre la
   que el modelo fue calibrado y evaluado, no solo el split de fit, y evita
   una base estadísticamente pobre si TRAIN es pequeño):
   - `annotation = annotation_repository.get_by_id(db, case.annotation_id)`
   - `study = annotation_repository.get_imaging_study(db, annotation)`
     (mismo helper que usa `training_service._cases_for_split`)
   - Si `annotation` o `study` es `None`, el caso se excluye (igual criterio
     que `_cases_for_split`, sin forzarlo).
   - `series_list = image_series_repository.list_for_study(db, study.id)`
   - Para cada serie: `segs = segmentation_repository.list_for_series(db, series.id)`;
     si `segs` no está vacío, se toma `segs[-1]` (la más reciente — mismo
     criterio "latest wins" que `analysis_service._latest_segmentation_biomarkers`).
   - `segmentation_repository.list_measurements(db, segs[-1].id)` — cada
     `BiomarkerMeasurement.name`/`value` se acumula en el pool base de ese
     `name`.
4. El resultado es, por cada `name` distinto visto: una lista de `value`
   flotantes — la muestra base para el KS test de ese biomarcador.

### 2. Ventana "reciente" — confirmación y query real

Confirmo la ventana propuesta por Liara con una regla única para
biomarcadores y predicciones, expresable en una sola query (evita la
ambigüedad de "100 o 30 días, lo que ocurra antes" con dos condiciones
sueltas):

```sql
... WHERE <timestamp_column> >= now() - interval '30 days'
ORDER BY <timestamp_column> DESC LIMIT 100
```

- **Biomarcadores recientes**: `BiomarkerMeasurement` no tiene columna de
  fecha propia útil más allá de `created_at` (heredada de
  `TimestampMixin`) — se usa esa. Consulta: todas las `BiomarkerMeasurement`
  cuyo `Segmentation.created_at >= now() - 30 días` (join
  `BiomarkerMeasurement.segmentation_id -> Segmentation`, ordenado por
  `Segmentation.created_at DESC`, `LIMIT 100` **por biomarcador** —
  el límite de 100 se aplica después de agrupar por `name`, no 100
  mediciones totales repartidas entre todos los biomarcadores). Nueva
  función en `segmentation_repository.py`:
  `list_recent_measurements_by_name(db, *, since: datetime, limit: int) -> dict[str, list[float]]`.
- **Predicciones recientes**: `AIAnalysis` con `status="COMPLETED"` y
  `model_version == f"{model_version.name}@{model_version.id}"` (ver punto
  3 — ese es el formato exacto que `analysis_service.execute_analysis` ya
  escribe, confirmado en el código real, no asumido), `completed_at >=
  now() - 30 días`, `ORDER BY completed_at DESC LIMIT 100`.

### 3. Servicio nuevo

`backend/app/services/drift_service.py`. Constantes de configuración (no
son decisión grande, ver "Regla de autonomía" — Tali puede ajustarlas sin
preguntar si hace falta, documentando en ADR si el ajuste es relevante):

```python
MIN_SAMPLE_SIZE = 30  # mínimo por muestra (base y reciente) para correr KS o PSI
RECENT_WINDOW_MAX_DAYS = 30
RECENT_WINDOW_MAX_ROWS = 100
BASE_PREDICTION_WINDOW_MAX_DAYS = 30
BASE_PREDICTION_WINDOW_MAX_ROWS = 100
KS_P_VALUE_THRESHOLD = 0.05
PSI_MODERATE_THRESHOLD = 0.1
PSI_SIGNIFICANT_THRESHOLD = 0.2
_CACHE_TTL_SECONDS = 300
```

Firmas principales:

```python
class ModelNotInProductionError(ValueError): ...

@dataclass
class BiomarkerDriftResult:
    biomarker_name: str
    ks_statistic: float | None
    p_value: float | None
    base_sample_size: int
    recent_sample_size: int
    drift_detected: bool
    skipped_reason: str | None  # set <=> los demás campos numéricos son None

@dataclass
class PredictionDriftResult:
    psi: float | None
    base_sample_size: int
    recent_sample_size: int
    severity: str  # "NONE" | "MODERATE" | "SIGNIFICANT"
    drift_detected: bool  # severity != "NONE"
    skipped_reason: str | None

@dataclass
class ModelDriftReport:
    model_version_id: uuid.UUID
    evaluated_at: datetime
    biomarkers: list[BiomarkerDriftResult]
    biomarkers_skipped_reason: str | None
    prediction: PredictionDriftResult

def get_drift_report(db: Session, *, model_version: ModelVersion) -> ModelDriftReport:
    """Único punto de entrada. Lanza ModelNotInProductionError si
    model_version.status != PRODUCTION (ver punto 4). Revisa la caché
    in-memory (ver punto 5) antes de recalcular; al recalcular, actualiza
    también los gauges de Prometheus como efecto secundario, en el mismo
    punto — nunca en el scrape de /metrics."""
```

`PredictionDriftResult.psi` se calcula sobre `AIAnalysis.predicted_class`
como variable categórica (no hace falta binning por cuantiles — ya es
categórica, con el conjunto fijo `training_service.ALL_DIAGNOSIS_LABELS`):
`PSI = Σ (p_recent_i - p_base_i) * ln(p_recent_i / p_base_i)` por cada
clase `i` en `ALL_DIAGNOSIS_LABELS`, con `epsilon=1e-4` sustituyendo
cualquier proporción en 0 (evita `ln(0)`, convención estándar de PSI).

La **base** de predicción (distinta del "dataset base" de biomarcadores)
son las primeras `min(100, N)` `AIAnalysis` COMPLETED con ese
`model_version` label, con `completed_at` dentro de los 30 días
siguientes al **evento de promoción más reciente** de ese
`model_version_id`: `audit_repository` ya registra
`action="model_version_promoted"`, `resource_type="model_version"`,
`resource_id=str(model_version.id)` (ver `model_service.promote`) — se
toma el `AuditEvent` más reciente con ese filtro (`ORDER BY occurred_at
DESC LIMIT 1`) como ancla `promoted_at`, y no el primero: si el modelo fue
retirado y vuelto a promover (rollback), la base debe reflejar el
comportamiento desde su reincorporación actual a producción, no arrastrar
predicciones de un período de producción anterior y distinto. Nueva
función en `audit_repository.py`:
`get_latest_event(db, *, action: str, resource_type: str, resource_id: str) -> AuditEvent | None`.
Si no hay evento de promoción (no debería ocurrir para un modelo
actualmente `PRODUCTION`, pero se maneja igual): `skipped_reason="no
promotion audit event found"`.

### 4. Endpoint

`GET /api/v1/model-versions/{model_version_id}/drift` — confirmado tal
cual lo propuso Liara. RBAC: mismo `_VIEW_ROLES = (ML_ENGINEER,
MODEL_APPROVER, ADMIN)` que `registry-divergence`/`evaluations` en
`app/api/v1/models.py` (solo lectura, ningún dato clínico/PII — igual
criterio de "no hace falta `security-review`" que el resto de endpoints de
gobernanza de modelos, ya que no expone datos de pacientes ni credenciales).
Declarado **después** de `/model-versions/{model_version_id}` en el router
(el prefijo es el mismo `{model_version_id}` que ya existe, no
`registry-divergence` que necesitaba ir antes por colisión de path — aquí
no hay colisión, `/drift` cuelga de un id ya parseado).

- 404 si el `model_version_id` no existe (mismo `_load_model_version`
  helper ya usado por el resto de rutas de `models.py`).
- **409 Conflict** si `model_version.status != PRODUCTION` — la deriva
  solo tiene una definición coherente respecto al `PRODUCTION` actual (la
  base de biomarcadores depende del `TrainingRun` que lo entrenó, la base
  de predicción depende de su evento de promoción). Pedir la deriva de un
  modelo `RETIRED`/`APPROVED` no tiene una respuesta bien definida con este
  diseño — se rechaza explícitamente en vez de devolver un resultado
  engañoso.
- 200 con `ModelDriftReport` serializado (`ModelDriftOut` en
  `app/schemas/model.py`, mismo patrón que `ModelRegistryDivergenceOut`).

### 5. Métricas Prometheus nuevas — nombres, labels, y cuándo se recalculan

Añadidas a `backend/app/core/metrics.py`, mismo módulo que las de EPIC-6.
Gauges (no Counter/Histogram — representan el último valor conocido, no un
acumulado):

```python
BIOMARKER_DRIFT_KS_STATISTIC = Gauge(
    "biomarker_drift_ks_statistic", "...", labelnames=("model_version_id", "biomarker_name"),
    multiprocess_mode="sum",
)
BIOMARKER_DRIFT_PVALUE = Gauge(
    "biomarker_drift_pvalue", "...", labelnames=("model_version_id", "biomarker_name"),
    multiprocess_mode="sum",
)
PREDICTION_DRIFT_PSI = Gauge(
    "prediction_drift_psi", "...", labelnames=("model_version_id",),
    multiprocess_mode="sum",
)
```

`multiprocess_mode="sum"` (no el default `"all"`): el cálculo de deriva
ocurre dentro del proceso `backend`/uvicorn que atendió la petición GET
`/drift` (nunca en el worker Celery, a diferencia de `dl_inference_*` —
esto es puramente de lectura, no hace falta el worker), y con
`PROMETHEUS_MULTIPROC_DIR` activo (ver `app/core/metrics.py` ya
existente) cada proceso uvicorn escribe en su propio archivo mmap. Como
solo un proceso a la vez llama `.set()` para un `model_version_id` dado
(el que atendió esa petición), `"sum"` across procesos da el valor real
sin duplicarlo ni necesitar el label `pid` que `"all"` añadiría. Si el
proceso que calculó muere sin limpiar, `_cleanup_stale_files_for_this_pid`
(ya existente) lo cubre igual que a las métricas de EPIC-6.

**Cuándo se recalculan — no en cada scrape**: recalcular en cada scrape
(cada ~15s) repetiría, por scrape, toda la traversal del punto 1
(potencialmente cientos de `DatasetCase` → estudio → series →
segmentaciones), cara comparada con leer un mmap. Los gauges se
actualizan **solo como efecto secundario de `drift_service.get_drift_report`**
(es decir, solo cuando alguien llama `GET /drift`), con una caché
in-memory a nivel de módulo (`dict[model_version_id, (computed_at,
ModelDriftReport)]`, TTL `_CACHE_TTL_SECONDS=300`) para que llamadas
repetidas al endpoint dentro de la ventana no vuelvan a golpear la base de
datos. Antes de la primera llamada a `/drift` para un `model_version_id`
dado (desde que ese proceso arrancó), esas series simplemente no existen
en `/metrics` — comportamiento correcto por defecto de `Gauge` (nunca se
inicializan con `.set(0)`, que se leería como "sin deriva" cuando en
realidad es "todavía no evaluado"). El panel de Grafana debe tratar la
ausencia de la serie como "sin datos", no como cero.

### 6. Umbrales — confirmados como estándar de industria

- **KS**: `p < 0.05` — el umbral de significancia convencional para un
  test de dos muestras, no un valor inventado para este proyecto.
- **PSI**: `PSI < 0.1` sin deriva relevante, `0.1 ≤ PSI ≤ 0.2` deriva
  moderada, `PSI > 0.2` deriva significativa — es la banda estándar citada
  en la literatura de model monitoring/credit-risk (no específica de
  ningún vendor). `drift_detected=true` en la respuesta cuando `severity
  != "NONE"` (es decir, `PSI ≥ 0.1` ya cuenta como señal a inspeccionar,
  aunque `severity` distingue moderada de significativa para que quien lea
  el resultado sepa la magnitud, no solo el binario).
- Ambos umbrales son constantes de módulo (punto 3), no vienen de
  variables de entorno en esta fase — si en el futuro hace falta
  configurarlos por despliegue, es un cambio menor (ver "Regla de
  autonomía"), no amerita ADR salvo que cambie el criterio en sí.

### 7. División de trabajo

Epic completa para **Tali** (`backend/app/services/drift_service.py`,
`backend/app/repositories/segmentation_repository.py` +
`audit_repository.py` (nuevas funciones), `backend/app/api/v1/models.py`
(endpoint nuevo), `backend/app/schemas/model.py` (schemas nuevos),
`backend/app/core/metrics.py` (gauges nuevos)). **No hace falta Garrus**:
no se toca `docker-compose.yml` (Prometheus ya scrapea `/metrics` desde
EPIC-6, y el multiprocess dir ya está montado en `backend` y `worker`) ni
se añade infraestructura nueva — los gauges nuevos aparecen solos en el
mismo scrape existente. Si Liara quiere un panel Grafana nuevo para estos
gauges en el dashboard de EPIC-6, eso puede ir en la misma Epic (edición
de un JSON de dashboard ya versionado, no infraestructura nueva) o como
fast-follow — lo dejo a su criterio de alcance, no es una decisión de
arquitectura.

## Verificación
- `backend`: 138/138 tests en verde (incluye 6 nuevos: drift forzado detectado con
  KS/p-value y PSI reales, ausencia de falso positivo sobre distribuciones equivalentes,
  409 si el modelo no está PRODUCTION, RBAC, 404, y omisión explícita de biomarcadores para
  un modelo DL sin `DatasetVersion` con `skipped_reason`), `ruff check` limpio.
- Sin migración: Epic puramente de lectura sobre datos ya existentes.
- `security-review` (skill del orquestador, combinado con EPIC-12): sin hallazgos — RBAC
  reutiliza exactamente `_VIEW_ROLES` de `registry-divergence`, queries parametrizadas vía
  ORM (sin SQL crudo), respuesta solo con estadísticos agregados (sin biomarcadores
  identificables por paciente).

## Estado
Completada
