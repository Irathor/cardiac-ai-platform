# EPIC-17: Selección de modelo al reentrenar + panel de validación completo (U-Net y CNN3D)

## Historia de usuario
Como administrador/ML Engineer, quiero elegir qué modelo reentrenar (nearest-centroid,
U-Net de segmentación o CNN3D de clasificación) desde el panel de administración, y ver tras
reentrenar todos los resultados de validación en una sola ventana con un conjunto amplio de
métricas, para poder verificar la calidad del modelo sin depender de scripts sueltos ejecutados
a mano sobre GPU.

## Tipo
Con IA (la Epic en su conjunto requiere disparar y evaluar entrenamiento real de modelos de
deep learning — U-Net y CNN3D — aunque las piezas de backend/frontend que la envuelven sean
CRUD/orquestación estándar sin necesitar por sí mismas a EDI).

## Bloqueada por
Ninguna (nearest-centroid ya existía; U-Net/CNN3D ya se entrenaban a mano con scripts en
`.venv-dl` — esta Epic los conecta al flujo de la aplicación, no depende de ninguna Epic previa
sin cerrar).

## Criterios de aceptación
- [x] El admin/ML Engineer puede elegir `model_type` (`NEAREST_CENTROID` | `UNET_SEGMENTATION`
      | `CNN3D_CLASSIFICATION`) al lanzar un reentrenamiento desde `POST
      /datasets/{id}/versions/{id}/training-runs` (body opcional, default `NEAREST_CENTROID`
      por compatibilidad) y desde `ModelTrainingPage` en el frontend.
- [x] Nearest-centroid sigue entrenando síncronamente dentro del worker Celery, sin cambios de
      comportamiento (regresión cubierta por test).
- [x] U-Net y CNN3D se disparan desde el worker Celery (Docker) hacia el servicio puente en el
      host (`ml/scripts/training_runner_service.py`), que ejecuta el script real ya existente
      en `.venv-dl` sobre GPU real y persiste `.pt` + métricas en `/data`, bind-mount compartido
      entre host y contenedores.
- [x] Si el servicio puente no está corriendo (o falla a mitad del job), el training run falla
      limpiamente con un mensaje claro — nunca queda colgado en `RUNNING` indefinidamente (poll
      con timeout, ver `execute_dl_training`).
- [x] Al completar un run (de cualquiera de los tres tipos), el admin ve en una sola pantalla
      (`ModelTrainingPage`, 5 pestañas) el conjunto mínimo obligatorio de métricas de validación
      que el usuario delimitó: resumen (curvas de loss, mejor época, overfitting), segmentación
      (Dice/IoU/HD95/ASSD/precision-recall-especificidad de vóxel/similitud volumétrica/error
      relativo de volumen/máscaras vacías/componentes conexas/violación anatómica heurística),
      clasificación (matriz de confusión, accuracy/balanced accuracy/precision/recall/
      especificidad/NPV/F1 por clase y macro/weighted/micro, MCC, Kappa, top-2 accuracy, ROC +
      AUC con IC 95% bootstrap por paciente, PR + AP/PR-AUC, Brier, log loss), calibración
      (reliability diagram, ECE, MCE, calibration slope/intercept, tasa de error con confianza
      >90%, curva riesgo-cobertura), biomarcadores (MAE, RMSE, sesgo, MAPE, Pearson, Spearman,
      ICC(3,1), R², Bland-Altman) y validación/robustez (resultados por fold, media/std/mediana/
      IQR, IC 95% bootstrap, comparación con baseline nearest-centroid) — para ambos modelos DL.
- [x] Lo que queda fuera del conjunto mínimo obligatorio (ver "Fuera de alcance") se muestra
      explícitamente como "no implementado en esta iteración" cuando aplica visualmente, nunca
      simulado con datos inventados.
- [x] El historial de runs pasados es consultable (no solo el último), para poder auditar
      cualquier ejecución anterior.
- [x] `ADMIN` puede disparar y leer entrenamientos/`model-versions`/evaluaciones igual que
      `ML_ENGINEER`, sin poder aprobar/promover/retirar un modelo (sigue siendo
      `MODEL_APPROVER`-only) — ver ADR-7 y `docs/permissions.md`.
- [x] Los modelos DL (U-Net, CNN3D) siguen entrenando contra `data/acdc-raw/...` en disco, no
      contra `DatasetVersion`/`cases` tabulares de nearest-centroid; `dataset_version_id` se
      sigue pidiendo en la URL por auditoría/consistencia de API pero no se usa como fuente de
      datos para tipos DL.

## Alcance
- **ml/EDI**: `ml/cardiac_ai_ml/dl/segmentation_metrics.py`, `biomarker_metrics.py`,
  `classification_metrics.py`, `fold_stats.py` (numpy/scipy/sklearn, sin duplicar
  `dl/metrics.py`); extensión de `train_segmentation.py`/`train_classification.py` para volcar
  el JSON de métricas ampliado; `ml/scripts/training_runner_service.py` (servidor HTTP stdlib
  sobre `.venv-dl`, sin dependencias nuevas).
- **backend/Tali**: migración `0007_dl_model_training.py`; `app/core/enums.py`
  (`TrainingModelType`); `app/core/model_registry.py` (`MODEL_NAME_UNET`/`MODEL_NAME_CNN3D`);
  `app/core/config.py` (`training_runner_url`, `data_root`); `app/api/v1/training.py` (rol
  `ADMIN`, body `model_type`); `app/api/v1/models.py` (rol `ADMIN` en `_VIEW_ROLES`);
  `app/services/training_service.py` (`execute_dl_training`); `app/tasks/training_tasks.py`
  (dispatch por `model_type`); `docs/permissions.md` (actualizado).
- **frontend/Miranda**: `frontend/src/api/training.ts`; `frontend/src/pages/
  ModelTrainingPage.tsx`; `frontend/src/components/training/{SummaryTab,SegmentationTab,
  ClassificationTab,CalibrationTab,ValidationTab}.tsx`; ruta `/admin/training` en `App.tsx`.
- **docker-compose/Garrus**: bind mount `./data:/data` en `backend` y `worker`.
- **tests/Mordin**: `ml/tests/dl/test_segmentation_metrics.py`,
  `test_classification_metrics.py`, `ml/tests/test_biomarker_metrics.py`,
  `backend/tests/test_training_api.py` (ADMIN, regresión nearest-centroid, `execute_dl_training`
  con runner mockeado), `frontend/tests/ModelTrainingPage.test.tsx`.

## Fuera de alcance
Se implementa el **conjunto mínimo obligatorio** de métricas que el propio usuario delimitó, no
las 174 métricas propuestas junto a él. Queda explícitamente fuera de esta iteración (documentado
como "no implementado", nunca simulado con datos falsos) — ver entrada correspondiente en
`docs/BACKLOG.md`:
- Batería de robustez sintética (ruido, rotación, contraste, slices faltantes, ficheros
  corruptos).
- Detección de out-of-distribution (OOD).
- Análisis por subgrupo, salvo lo trivialmente disponible con los datos ya calculados.
- Métricas de latencia/throughput/hardware.
- Refactor/optimización más allá del código que esta Epic toca directamente (no es una
  reescritura del resto de la plataforma).

### Ajuste post-cierre (bug real encontrado en verificación en vivo)
Al verificar en vivo (levantar el runner + `docker compose up` + disparar un reentrenamiento
real de U-Net desde `/admin/training` como `ADMIN`), apareció un bug real no cubierto por los
tests existentes (que solo probaban `ML_ENGINEER`): `GET /api/v1/datasets` seguía siendo
`ML_ENGINEER`-only, nunca se le añadió `ADMIN` como al resto de endpoints de esta Epic. El
frontend usa ese listado para auto-rellenar `datasetId`/`versionId` — necesarios en la URL
incluso para los tipos DL, solo como identificador de auditoría (ver "Contrato técnico" punto
1) — así que el 403 dejaba el botón "Start training" permanentemente deshabilitado para
`ADMIN`, para los tres tipos de modelo, no solo nearest-centroid. Corregido añadiendo `ADMIN`
a los tres endpoints de solo lectura de `datasets.py` (`list_datasets`, `get_dataset`,
`list_dataset_versions`) — no a los de creación (`create_dataset`, `create_dataset_version`),
que siguen siendo `ML_ENGINEER`-only, tal como ya documentaba `docs/permissions.md` ("Configure/
start/... training runs" ya listaba `ADMIN` ✅, este fix solo hace el código consistente con lo
que ya estaba documentado). Verificado con `pytest tests/test_dataset_api.py tests/test_permissions.py
tests/test_training_api.py` (28/28) y con el flujo real end-to-end: reentrenamiento de U-Net
disparado de verdad desde la UI como `ADMIN`, GPU real confirmada (`device: cuda`, 85/15/50
pacientes train/val/test reales de ACDC).

## Estado
Completada

## Contrato técnico (Shepard)

### 1. Flujo end-to-end
```
Admin/ML_ENGINEER (frontend)
  -> POST /training-runs {model_type, dataset_version_id?}
  -> Celery task run_training
      NEAREST_CENTROID -> execute_training (sin cambios, sincrono, en el propio worker)
      UNET_SEGMENTATION | CNN3D_CLASSIFICATION -> execute_dl_training
           -> POST http://host.docker.internal:8800/jobs {model_type}
           -> poll GET .../jobs/{id} hasta COMPLETED/FAILED (bloqueante dentro de la task)
           -> runner ejecuta el script real (.venv-dl, GPU), escribe .pt + metrics.json
              ampliado en /data/models/... (bind mount compartido)
           -> task lee ese JSON desde /data (mismo volumen, sin transferir el archivo por HTTP)
           -> persiste ModelVersion + ModelEvaluation(metrics=JSON completo) + log a MLflow
  Frontend hace polling de GET /training-runs/{id} y, al completar, renderiza las 5 pestañas
```

### 2. Servicio puente en el host — prerequisito manual, nunca arrancado por Celery
`ml/scripts/training_runner_service.py` es un HTTP server mínimo (stdlib, sin dependencias
nuevas) que corre en el host dentro de `.venv-dl`. El worker Celery (contenedor) lo alcanza vía
`http://host.docker.internal:8800`. Si no está corriendo, el training run falla limpiamente
(nunca se queda colgado en `RUNNING`) — ver ADR-8 y `docs/dl-training-runner.md` para el
razonamiento completo y cómo arrancarlo.

### 3. RBAC — ADMIN como rol adicional, no sustituto
Se añade `ADMIN` a los endpoints de entrenamiento (`POST/GET .../training-runs*`) y de lectura
de `model-versions`/evaluaciones, manteniendo `MODEL_APPROVER` como único rol que aprueba/
promueve/retira un modelo. Es una desviación explícita de la matriz de permisos previa — ver
ADR-7 y `docs/permissions.md` (sección "Explicit denials").

### 4. División de trabajo
ml/EDI construye los módulos de métricas y el servicio puente; backend/Tali conecta el flujo de
entrenamiento y RBAC; frontend/Miranda construye `ModelTrainingPage` y sus 5 pestañas;
docker-compose/Garrus añade el bind mount `./data`; tests/Mordin cubre las tres capas.

### 5. Seguridad
`security-review` aplica por RBAC nuevo (`ADMIN` sobre endpoints de entrenamiento) y por el
servicio puente nuevo expuesto en el host — ejecutado por el orquestador al cierre de esta Epic,
combinado con la verificación end-to-end de la sección "Verificación".

## Verificación
- `pytest ml/` (venv ligero) y `pytest ml/ -x` con `.venv-dl` para los nuevos módulos de
  métricas: en verde.
- `pytest backend/` completo (incluye regresión nearest-centroid + flujo DL con runner
  mockeado): en verde.
- Runner (`.venv-dl`) + `docker compose up` + reentrenamiento real de U-Net y de CNN3D desde la
  UI: las 5 pestañas muestran datos reales al completar, sin regresión sobre nearest-centroid.
- `npm run lint && npm run build && npm test` en `frontend/`: en verde.
- `security-review`: sin hallazgos bloqueantes sobre el RBAC nuevo ni sobre el servicio puente
  (limitado a `localhost`/red del host, sin autenticación propia — aceptado como parte de
  ADR-8, ver sus "Consecuencias").
