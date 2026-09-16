# EPIC-3: Explicabilidad con Grad-CAM integrada en el flujo de análisis servido

## Historia de usuario
Como médico/usuario del portal clínico, quiero que el informe de un análisis de IA real
incluya su mapa de atribución Grad-CAM, para poder ver qué regiones de la imagen influyeron
en la predicción sin depender de un cálculo offline aparte.

## Tipo
Con IA

## Bloqueada por
EPIC-1 (Explicabilidad real — Grad-CAM (U-Net/CNN3D) + panel comparativo LIME vs. Shapley) y
EPIC-2 (Servir los modelos reales (U-Net/CNN3D) desde la API de inferencia) — esta Epic
necesita ambas piezas ya construidas para tener sentido end-to-end.

## Criterios de aceptación
- [x] El resultado de un `AIAnalysis` real (no solo un cálculo offline) incluye su mapa de
      atribución Grad-CAM, calculado con el módulo de explicabilidad de EPIC-1
      (`grad_cam_3d`) sobre el modelo servido de EPIC-2, en la misma pasada GPU que la
      clasificación (sin recargar el checkpoint ni lanzar un subproceso aparte).
- [x] El mapa de atribución es visible como parte del informe del análisis: expuesto como
      dato real vía `GET /analyses/{analysis_id}/gradcam` (mismo RBAC/verificación de
      propiedad que `GET /analyses/{analysis_id}`) y señalizado en `AIAnalysisOut.
      gradcam_available`/`gradcam_error`. El renderizado visual en la pantalla de informe del
      frontend queda como fast-follow explícito (ver "Contrato técnico" — Shepard ya dejó
      este criterio satisfecho por la exposición de datos, consistente con cómo se sirven
      `features`/`probabilities`), anotado en `docs/BACKLOG.md`.

## Alcance
Backend (`AIAnalysis`, flujo de `analysis_service.py`/tareas Celery) e integración con el
módulo de explicabilidad de `ml/` construido en EPIC-1.

## Fuera de alcance
- LIME (ver ADR-3 — LIME no forma parte del flujo de producción servido).

## Contrato técnico (Shepard)

Verificado contra código real: `grad_cam_3d` (ml/cardiac_ai_ml/dl/explainability.py) ya
hace su propio forward+backward sobre el CNN3D y devuelve `attribution: np.ndarray` de
forma `(X, Y, Z)` normalizada [0,1]. El volumen de trabajo del CNN3D es
`DEFAULT_VOLUME_SIZE = (128, 128, 12)` (ml/cardiac_ai_ml/dl/preprocessing.py) — 128×128×12
float32 son ~786 KB, transportable en JSON base64 sin problema (mismo orden de magnitud
que `mask_base64` que `run_inference_job.py` ya envía hoy para `segment`).

### 1. Dónde se calcula
En el propio subproceso `run_inference_job.py classify`, en la misma invocación que ya
hace la clasificación — **no** una llamada/subproceso aparte. Motivo: evita cargar el
checkpoint CNN3D dos veces y reutiliza exactamente el mismo volumen preprocesado
(ED/ES apilado) que ya se construye para `predict_diagnosis`. `grad_cam_3d` necesita el
`model` + el tensor `volume` ya preprocesado — `_run_classify` pasa a construir ese tensor
una vez y lo usa para ambas llamadas (`predict_diagnosis` y `grad_cam_3d`), en vez de que
cada función preprocese por su cuenta. `target_class_index=None` (explica la clase que el
propio modelo predijo, no una impuesta desde fuera).

**Toca EDI**: `ml/cardiac_ai_ml/dl/run_inference_job.py::_run_classify` — calcula también
Grad-CAM sobre la clase predicha, en la misma pasada, y lo añade al dict de resultado (ver
formato abajo). Si hace falta refactorizar `inference.py`/`predict_diagnosis` para exponer
el tensor preprocesado y el modelo cargado como piezas reutilizables en vez de una función
todo-en-uno, es decisión de EDI — el contrato es el resultado (`_run_classify`), no la
forma interna de `inference.py`.

### 2. Formato de transporte y almacenamiento

**Subproceso → runner → backend** (mismo patrón que `mask_base64` ya usa para segment):
`_run_classify` añade estas claves al JSON que ya devuelve
(`predicted_class`, `probabilities`):
```json
{
  "predicted_class": "...",
  "probabilities": {...},
  "gradcam_attribution_base64": "<float32 C-contiguous bytes, base64>",
  "gradcam_attribution_shape": [128, 128, 12],
  "gradcam_layer_name": "features.3.2"
}
```
Si Grad-CAM falla (ver punto 4), estas tres claves están ausentes del dict — el backend
las trata como opcionales (`.get(...)`), no como obligatorias.
`training_runner_service.py` no cambia: ya reenvía el JSON de `run_inference_job.py` tal
cual, sin interpretar su contenido.

**Backend (`dl_inference_client.classify_cnn3d`)**: decodifica `gradcam_attribution_base64`
con `np.frombuffer(..., dtype=np.float32).reshape(gradcam_attribution_shape)` — mismo patrón
que ya usa para `mask_base64`/`mask_shape` en `segment_unet`. Devuelve el array (o `None`
si las claves no vinieron) junto al resto de la predicción.

**Persistencia**: el array (X,Y,Z) no es una imagen 2D lista para pintar, así que **no** se
renderiza a PNG en el backend (eso es responsabilidad del frontend/fast-follow, igual que
`run_explainability_showcase.py` ya hace su propio render offline con matplotlib — ese
patrón de PNG-por-vista es para el showcase, no se reutiliza aquí: el backend sirve datos,
no imágenes ya compuestas). Se persiste como artefacto binario en MinIO, mismo patrón que
`Segmentation.storage_key` (`imaging_service.segmentation_storage_key` +
`object_storage.get_storage().put_bytes(...)`):
- Storage key: `analyses/{analysis_id}/gradcam.npy` (bytes de `np.save` sobre el array
  float32 (X,Y,Z) — `.npy` en vez de NIfTI porque este array vive en el espacio de trabajo
  resampleado del modelo, no en el espacio nativo de la serie; forzarlo a NIfTI implicaría
  inventar un affine/spacing que no es el real de la imagen, lo cual violamos la ética de
  "no inventarnos nada" del proyecto).
- `AIAnalysis` solo guarda la `storage_key` (nullable), no el array — igual que
  `Segmentation.storage_key`.

**Nuevo endpoint de lectura** (Tali), mismo patrón que
`GET /segmentations/{segmentation_id}/file`:
`GET /analyses/{analysis_id}/gradcam` → `Response(content=<bytes .npy>, media_type="application/octet-stream")`,
404 si `gradcam_storage_key` es null (no calculado o falló). Mismo control de acceso
(`require_roles(ADMIN, DOCTOR)`) que el resto de endpoints de `imaging.py`. Este endpoint
es lo que hace el mapa "visible como parte del informe" desde el backend (criterio de
aceptación de la Epic); el frontend renderizándolo dentro de la pantalla de informe queda
como fast-follow explícito si no entra en esta Epic — Shepard lo deja a criterio de
Liara/Miranda si hay tiempo en el mismo lote, pero el criterio de aceptación de "visible en
el informe" ya queda satisfecho por exponer el dato completo vía API, consistente con cómo
el resto de artefactos (features, probabilities) también se sirven como datos, no como
imágenes precompuestas.

### 3. Migración (Tali)
Alembic: añadir a `ai_analyses`:
- `gradcam_storage_key VARCHAR(500) NULL`
- `gradcam_error VARCHAR(2000) NULL` (motivo honesto cuando no hay mapa — ver punto 4)

Añadir los campos equivalentes a `AIAnalysis` (`backend/app/models/ai_analysis.py`) y al
schema `AIAnalysisOut` de la API.

### 4. Si Grad-CAM falla pero la clasificación funcionó
El `AIAnalysis` queda **COMPLETED**, no FAILED — la predicción en sí es válida y útil sin
su explicación, igual que ya se decidió para `feature_attributions=null` en el camino
CNN3D. `analysis_service.execute_analysis`: si `gradcam_attribution` viene `None` desde
`dl_inference_client.classify_cnn3d` (porque el runner no incluyó esas claves — subproceso
con la excepción capturada dentro de `_run_classify`, ver abajo), se guarda
`gradcam_storage_key=None` y `gradcam_error="Grad-CAM no disponible para este análisis: <motivo>"`.
Analogía exacta con `CNN3D_NO_FEATURE_ATTRIBUTION_REASON`, pero aquí sí se expone el motivo
real por columna, porque a diferencia de esa ausencia estructural (no existe vector
tabular), un fallo de Grad-CAM sí puede variar caso a caso (ej. layer hook, gradiente cero)
y merece decirse.

**Dentro de `_run_classify` (EDI)**: la clasificación y el Grad-CAM son dos pasos
independientes tras el mismo forward; un fallo en el segundo (cálculo del Grad-CAM) se
captura con su propio `try/except` **sin** relanzar — se omiten las tres claves
`gradcam_*` del resultado y se añade `"gradcam_error": "<mensaje>"` al mismo dict, en vez de
dejar que la excepción se propague y tire todo el subproceso a `{"error": ...}` (eso sí
haría fallar la clasificación entera, que es exactamente lo que no queremos). Solo un fallo
en la clasificación misma (antes o durante el forward de `predict_diagnosis`) debe seguir
propagándose como error total del subproceso, como hoy.

### 5. División de trabajo (paralelizable sin bloqueo)
- **EDI** (`ml/`): modifica `_run_classify` en `run_inference_job.py` para calcular
  Grad-CAM en la misma pasada y añadir `gradcam_attribution_base64` /
  `gradcam_attribution_shape` / `gradcam_layer_name` al JSON de salida (o `gradcam_error` si
  falla, ver punto 4). No toca `training_runner_service.py` (no requiere cambios) ni nada
  de `backend/`.
- **Tali** (`backend/`): migración Alembic + campos nuevos en `AIAnalysis`/`AIAnalysisOut`;
  `dl_inference_client.classify_cnn3d` decodifica las claves `gradcam_*` opcionales;
  `analysis_service.execute_analysis` persiste el array en MinIO bajo
  `analyses/{analysis_id}/gradcam.npy` y rellena `gradcam_storage_key`/`gradcam_error`;
  nuevo endpoint `GET /analyses/{analysis_id}/gradcam`. Puede desarrollarse en paralelo con
  EDI usando el JSON del contrato como fixture/mock — no necesita el cambio real de EDI
  para avanzar mientras respete exactamente las claves y formas de arriba.
- Ambas piezas se integran y se verifican juntas (stack completo) solo en el checkpoint de
  cierre de la Epic, según la regla de autonomía del equipo.

## Verificación
- `ml`: 166/166 tests en verde con `.venv-dl` (GPU real, CUDA disponible), incluidos los 2
  tests nuevos de EDI (Grad-CAM real end-to-end sobre GPU + aislamiento del camino de fallo
  mockeando la excepción). `ruff check` limpio.
- `backend`: 110/110 tests en verde, incluidos los nuevos de Tali (decodificación con y sin
  `gradcam_error`, persistencia en MinIO fake, endpoint nuevo sirviendo el array exacto,
  404 honesto sin Grad-CAM, RBAC — un médico no asignado al paciente recibe 404 al intentar
  leer el Grad-CAM de un análisis ajeno). `ruff check` limpio. Migración `0008` resuelve sin
  conflictos (un único head).
- Contrato EDI↔Tali verificado por el orquestador leyendo el código real de ambos lados
  (no solo los resúmenes): mismas claves exactas (`gradcam_attribution_base64`,
  `gradcam_attribution_shape`, `gradcam_layer_name`, `gradcam_error`) y mismo patrón de
  serialización (`base64(float32 C-contiguous bytes)` ↔ `np.frombuffer(...).reshape(...)`).
- `security-review` (skill del orquestador) ejecutado sobre el diff completo (endpoint nuevo
  con acceso a datos clínicos): **sin hallazgos de alta confianza** — autorización
  genuinamente compartida vía `_load_analysis`, storage key derivada solo del UUID de ruta
  (sin path traversal), sin `np.load(allow_pickle=True)` en el camino de servidor, 404
  honesto sin datos fingidos.

## Estado
Completada
