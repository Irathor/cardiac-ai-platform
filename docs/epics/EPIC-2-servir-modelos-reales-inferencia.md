# EPIC-2: Servir los modelos reales (U-Net/CNN3D) desde la API de inferencia

## Historia de usuario
Como ingeniero de ML que presenta este proyecto como portfolio, quiero que la API de
inferencia sirva los modelos reales ya entrenados (U-Net/CNN3D) cuando corresponda, en vez
de servir siempre el clasificador heurístico nearest-centroid, para que el flujo end-to-end
del sistema use modelos genuinamente entrenados.

## Tipo
Con IA

## Bloqueada por
Ninguna (tiene más sentido implementarse después de EPIC-1, pero no depende técnicamente de
ella).

## Refinamiento de alcance (decidido al arrancar la implementación)

El texto original agrupaba U-Net y CNN3D como si ambos se sirvieran igual desde
`analysis_service.py`/`AIAnalysis`. Revisando el modelo de dominio real, no es así:

- **CNN3D_CLASSIFICATION** SÍ se sirve desde `analysis_service.py`/`AIAnalysis` — es un
  clasificador de diagnóstico, igual que nearest-centroid, produce `predicted_class`/
  `probabilities`/`confidence`. `features`/`feature_attributions` quedan `null` de forma
  honesta (no fabricados): no existe un vector de biomarcadores tabular que un modelo
  imagen-nativo haya usado para clasificar — ver `CNN3D_NO_FEATURE_ATTRIBUTION_REASON` en
  `analysis_service.py`. Grad-CAM real sobre este modelo es EPIC-3, no esta Epic.
- **UNET_SEGMENTATION** NO es un clasificador de diagnóstico, es un modelo de segmentación —
  no encaja en `AIAnalysis`. Se implementó como una capacidad nueva de **auto-segmentación**:
  cuando el `ModelVersion` PRODUCTION `cardiac-segmentation-unet` existe, el sistema puede
  generar una `Segmentation` real (la misma entidad que ya usa una máscara subida a mano)
  corriendo el U-Net sobre una `ImageSeries` ya subida — `POST /series/{id}/auto-segmentation`,
  mismo RBAC (ADMIN/DOCTOR) que subir una segmentación manualmente. Reutiliza
  `compute_frame_biomarkers` (el mismo cálculo que usa cualquier segmentación) y la misma
  convención de storage key; no reutiliza `imaging_service.upload_segmentation` directamente
  porque esa función valida que la máscara tenga la forma nativa de la serie, y el U-Net
  predice deliberadamente a su propia resolución de trabajo (ver docstring de
  `auto_segmentation_service.py`).

## Decisión técnica: GPU real vía el runner existente, no CPU en el contenedor

El entrenamiento (`ml/scripts/training_runner_service.py`) necesita GPU real y corre en el
host vía un puente HTTP porque el contenedor `worker` no tiene passthrough de GPU (ver
`docs/dl-training-runner.md`). La inferencia en tiempo real (un único forward pass) reutiliza
exactamente ese mismo puente en vez de instalar `torch`/`monai` en el contenedor
`backend`/`worker`:

- `ml/scripts/training_runner_service.py` gana dos endpoints nuevos, `POST /inference/classify`
  (CNN3D) y `POST /inference/segment` (U-Net), documentados en `docs/dl-training-runner.md`.
  A diferencia de `/jobs` (que lanza un subproceso y se sondea porque una época de
  entrenamiento tarda minutos/horas), estos son síncronos: un forward pass tarda
  milisegundos-segundos, así que el runner lanza `python -m cardiac_ai_ml.dl.run_inference_job`
  como subproceso corto y bloquea hasta que termina.
- **Requieren GPU real explícitamente, sin fallback silencioso a CPU** — ver
  `cardiac_ai_ml.dl.inference._require_cuda_device`. Si no hay CUDA disponible en el proceso
  (`.venv-dl` sin build CUDA, o sin GPU), la inferencia falla con un `RuntimeError` claro, nunca
  continúa en CPU fingiendo un resultado equivalente. A diferencia de los scripts de
  entrenamiento (donde `"cuda" if torch.cuda.is_available() else "cpu"` es aceptable para un
  smoke test rápido), aquí no lo es: un forward pass en CPU produce un resultado con la misma
  forma que uno real, así que serví­rlo en silencio parecería un despliegue funcionando
  mientras corre numéricas nunca validadas para este uso.
- `backend`/`worker` **no** ganan el extra `dl` de `ml/pyproject.toml` — siguen sin
  torch/monai instalados, sin cambios en `backend/Dockerfile` ni en `docker-compose.yml` (el
  bind mount `./data:/data` que la inferencia necesita para intercambiar archivos con el
  runner ya existía en ambos servicios antes de esta Epic). `backend/app/services/
  dl_inference_client.py` hace de puente HTTP — mismo patrón que
  `training_service.execute_dl_training` ya usa para `/jobs`, reutilizando
  `settings.training_runner_url`.
- El prerequisito manual de "el runner tiene que estar arrancado en el host" ya existía y ya
  estaba documentado para el entrenamiento; ahora aplica también a la inferencia. Si el runner
  no está corriendo, la llamada falla con un `InferenceRunnerError` claro (503 en el endpoint
  de auto-segmentación; `AIAnalysis` queda `FAILED` con el mensaje real), nunca cuelga ni
  finge un resultado.

## Criterios de aceptación
- [x] `analysis_service.py` deja de servir siempre el clasificador nearest-centroid: cuando el
      modelo marcado `PRODUCTION` es `CNN3D_CLASSIFICATION`, la inferencia real corre esos
      pesos entrenados (vía el runner, ver arriba). `UNET_SEGMENTATION` se sirve por la nueva
      auto-segmentación (`Segmentation`, no `AIAnalysis` — ver refinamiento de alcance arriba).
- [x] Queda decidido y documentado que la inferencia servida requiere el mismo runner con GPU
      real que el entrenamiento (nunca CPU) — ver "Decisión técnica" arriba y
      `docs/dl-training-runner.md`.
- [x] El comportamiento existente (servir el clasificador heurístico/nearest-centroid cuando
      no hay un CNN3D PRODUCTION) se mantiene sin regresión — ver "Verificación" abajo.

## Alcance
- `backend/app/services/analysis_service.py` (CNN3D real en `AIAnalysis`).
- `backend/app/services/auto_segmentation_service.py` (nuevo — U-Net real en `Segmentation`) y
  `backend/app/api/v1/imaging.py` (`POST /series/{id}/auto-segmentation`).
- `backend/app/services/dl_inference_client.py` (nuevo — puente HTTP al runner).
- `ml/scripts/training_runner_service.py` (`/inference/classify`, `/inference/segment`) y
  `ml/cardiac_ai_ml/dl/inference.py` + `run_inference_job.py` (nuevos).

## Fuera de alcance
- Entrenamiento de los modelos (ya existe, Fases 7-8).
- El registro de modelos (ya existe; su evolución hacia el híbrido MLflow/tabla propia es
  EPIC-4).
- Grad-CAM/explicabilidad real sobre el CNN3D dentro de `AIAnalysis` (EPIC-3).

## Verificación
- `backend`: 104/104 tests existentes en verde + 36 tests nuevos/tocados
  (`test_analysis_api.py`, `test_auto_segmentation_api.py`, `test_dl_inference_client.py`,
  `test_imaging_api.py`, `test_training_api.py`) — regresión cero confirmada en el camino
  nearest-centroid. `ruff check` en verde.
- `ml`: 164/164 tests en verde con `.venv-dl` (torch+CUDA reales instalados en este host),
  incluidos los nuevos `tests/dl/test_inference.py` (checkpoints reales, sin entrenar, cargados
  y corridos de verdad sobre GPU real) y `tests/dl/test_run_inference_job.py`.
- End-to-end real: se levantó `training_runner_service.py` de verdad sobre `.venv-dl` (GPU
  real) y se golpearon `POST /inference/segment`/`POST /inference/classify` con NIfTI
  sintéticos reales, contra los checkpoints reales entrenados
  (`data/models/unet2d.pt`/`data/models/cnn3d/cnn3d.pt`) — 200 con máscara/predicción reales
  en ambos casos; también se verificaron los caminos de error (checkpoint no encontrado, path
  traversal, campo faltante).
- No se levantó el stack completo de Docker Compose (backend/worker en contenedor) contra el
  runner real en este cierre — los contenedores no cambiaron (mismo `Dockerfile`/
  `docker-compose.yml` de antes de esta Epic), así que el riesgo real estaba en el código
  Python nuevo, que sí se verificó de las formas de arriba.

## Estado
Completada
