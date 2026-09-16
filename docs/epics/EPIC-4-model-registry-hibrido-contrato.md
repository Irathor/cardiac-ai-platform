# EPIC-4: Contrato y esquema del Model Registry (híbrido propio + MLflow nativo)

## Historia de usuario
Como ingeniero de ML/MLOps, quiero que el Model Registry nativo de MLflow y el registro
propio con aprobación humana trabajen juntos de forma consistente, para tener trazabilidad
estándar de artefactos sin perder el requisito de justificación humana obligatoria del
proyecto.

## Tipo
Normal

## Bloqueada por
Ninguna

## Criterios de aceptación
- [x] Se implementa el modelo híbrido decidido en ADR-2: `mlflow.register_model(...)` se
      llama al terminar cada training run (antes de crear la fila `ModelVersion`, sin
      posibilidad de divergencia por construcción en ese punto), y `MlflowClient().
      transition_model_version_stage(...)` refleja cada cambio de `status` propio como stage
      técnico de MLflow (`APPROVED→Staging`, `PRODUCTION→Production`, `REJECTED`/
      `RETIRED→Archived`). La tabla propia sigue siendo la única fuente de verdad del flujo
      de aprobación humana con justificación obligatoria — sin cambios en `review()`/
      `promote()` de cara al cliente.
- [x] Sincronización documentada en la sección "Contrato técnico (Shepard)" abajo: registro
      del artefacto dentro del mismo `try` de `execute_training`/`execute_dl_training`
      (`training_service.py`), transición de stage en el mismo commit lógico que el cambio de
      `status` (`model_service.py::_transition_stage`).
- [x] Divergencia: `GET /api/v1/model-versions/registry-divergence` (solo lectura, RBAC
      `_VIEW_ROLES` ya existente) compara stage esperado vs. real por cada `ModelVersion`. La
      tabla propia gana como fuente de verdad de negocio; corregir MLflow es una acción
      humana explícita, fuera de esta Epic (fast-follow en `docs/BACKLOG.md`).
- [x] `review()`/`promote()` mantienen firma, excepciones (`MissingJustificationError`,
      `InvalidModelStateError`) y forma de retorno sin cambios — el único comportamiento
      nuevo observable es el 502 (`ModelRegistrySyncError`) si MLflow no responde, y el
      cambio de `status` local nunca queda persistido en ese caso.

## Alcance
`backend/app/models/model_version.py`, `backend/app/models/model_approval.py`,
`backend/app/services/model_service.py`, `backend/app/services/training_service.py`,
integración con el Model Registry nativo de MLflow.

## Fuera de alcance
Cambios en el flujo de aprobación humano con justificación, que se mantiene igual (ver
ADR-2).

## Verificación
- `backend`: 124/124 tests en verde (incluye los 2 de regresión añadidos en el checkpoint de
  cierre, ver abajo), `ruff check` limpio, migración `0009` encadena sin conflictos sobre
  `0008` (un único head).
- `security-review` (skill del orquestador) ejecutado sobre el diff completo: RBAC del
  endpoint nuevo reutiliza `_VIEW_ROLES` ya existente sin bypass, sin inyección (todos los
  identificadores van como kwargs al SDK de MLflow, nunca interpolados), confirmado que un
  fallo de `_transition_stage` nunca deja el `status` local commiteado (solo hay
  `db.flush()`, nunca `db.commit()`, antes de la llamada a MLflow).
- **2 hallazgos MEDIUM reales del security-review, corregidos en este mismo checkpoint** (no
  ameritaban relanzar un subagente — son el tipo de fix que la convención del equipo asigna
  a quien verifica):
  1. `promote()` dejaba una inconsistencia real si la segunda transición MLflow (demover la
     versión anterior a `Archived`) fallaba después de que la primera (promover la nueva a
     `Production`) ya hubiera tenido éxito: el `status` local revertía pero MLflow seguía
     mostrando la nueva versión como `Production`. Arreglado con un revert best-effort de la
     primera transición cuando la segunda falla (`model_service.py::promote`) — test de
     regresión: `test_promote_reverts_the_first_mlflow_transition_when_the_second_fails`.
  2. El sentinel `mlflow_registry_version="0"` del backfill de la migración `0009` (filas
     `ModelVersion` previas a esta Epic, sin contrapartida real en MLflow) hacía que
     `check_registry_divergence()` lanzara `ModelRegistrySyncError` y tumbara con 502 **todo**
     el reporte de divergencia por una sola fila antigua, inhabilitando la propia herramienta
     de gobernanza pensada para detectar problemas como el punto 1. Arreglado: un fallo de
     lectura por fila se reporta ahora como una entrada de divergencia con `fetch_error`
     (campo nuevo en `RegistryDivergence`/`ModelRegistryDivergenceOut`), sin abortar el resto
     del reporte — test de regresión:
     `test_registry_divergence_endpoint_reports_an_unreachable_version_without_failing_the_whole_report`.

## Estado
Completada

## Contrato técnico (Shepard)

Verificado contra el código real (`backend/app/services/training_service.py`,
`backend/app/services/model_service.py`, `backend/app/models/model_version.py`,
`backend/app/api/v1/models.py`, `backend/app/db/session.py`) antes de decidir. Hoy
`mlflow.register_model` y `MlflowClient().transition_model_version_stage` no se llaman en
ningún sitio — solo se usa `mlflow.start_run`/`log_*` (tracking de runs).

### 1. Registro del artefacto — opción (a), en el momento del training

`mlflow.register_model(...)` se llama **dentro del mismo `try` de
`execute_training`/`execute_dl_training`**, justo después de que se cierra el bloque
`with mlflow.start_run()` y **antes** de `model_repository.create(...)`. Criterio: el
artefacto ya es real en cuanto termina el run — la aprobación humana no decide si el
artefacto *existe* en el Registry, solo si se promueve. Registrar en (b) o (c) dejaría
versiones "candidatas" sin ningún rastro en el Registry nativo mientras están
`PENDING_REVIEW`, que es justo el tramo donde más se necesita trazabilidad de lineage.

Detalle de implementación importante (el campo `mlflow_model_uri` ya guardado
**no** es un URI válido para `register_model` — es la ruta absoluta del artifact
store, ej. `s3://.../prototypes.json`). `register_model` necesita el formato
`runs:/<run_id>/<artifact_path>`:

```python
registered = mlflow.register_model(
    model_uri=f"runs:/{mlflow_run_id}/{artifact_path}",  # "prototypes.json" o el nombre del .pt
    name=model_name,  # MODEL_NAME / MODEL_NAME_UNET / MODEL_NAME_CNN3D — reutiliza
                       # las constantes ya centralizadas en app.core.model_registry,
                       # el mismo nombre que ya se usa como experiment
)
```

`mlflow_model_uri` (el campo existente) no cambia de significado ni de formato — sigue
siendo la URI absoluta del artifact store, para referencia/descarga. La referencia al
Registry nativo se guarda en los dos campos nuevos del punto 3.

Si `register_model` lanza excepción, cae en el mismo `except Exception` ya existente
que envuelve todo el bloque: el run se marca `FAILED` y **no se crea fila
`ModelVersion`** — mismo comportamiento que hoy tiene un fallo de `mlflow.log_*`. No
hace falta lógica de compensación nueva: ya es imposible que quede un run `COMPLETED`
sin su artefacto registrado, porque el registro ocurre antes de que exista la fila
`ModelVersion` que lo referenciaría.

### 2. Stage técnico de MLflow — mapeo y disparo

Mapeo `ModelVersionStatus` → stage nativo de MLflow:

| `ModelVersionStatus` propio | Stage MLflow    |
|---|---|
| `PENDING_REVIEW`            | `None` (el que asigna `register_model` por defecto, sin acción) |
| `APPROVED`                  | `Staging` |
| `REJECTED`                  | `Archived` |
| `PRODUCTION`                | `Production` |
| `RETIRED`                   | `Archived` |

Disparo, en el **mismo commit atómico de request** (misma función, antes de que la
ruta llame a `db.commit()` — ver punto 4 para el porqué esto basta sin transacción
distribuida real):
- `model_service.review()`: tras fijar `model_version.status`, llama a
  `MlflowClient().transition_model_version_stage(name=mlflow_registry_name,
  version=mlflow_registry_version, stage="Staging" | "Archived",
  archive_existing_versions=False)` — `archive_existing_versions=False` explícito
  porque el archivado de la versión previa en producción lo gestiona `promote()`
  explícitamente, no el mecanismo automático de MLflow.
- `model_service.promote()`: transiciona la versión promovida a `Production`, y si
  existe `current_production`, transiciona también **esa** versión (su
  `mlflow_registry_name`/`mlflow_registry_version` propios) a `Archived` — refleja
  exactamente lo que ya hace hoy con `current_production.status = RETIRED`.

**Si la llamada a MLflow falla**: no se revierte manualmente nada porque nunca llega a
haber nada que revertir — ver punto 4, la respuesta corta es que la excepción se
propaga y el cambio de `status` local (solo `flush`eado, no `commit`eado) se descarta
solo al cerrarse la sesión.

### 3. Campos nuevos en `ModelVersion`

```python
mlflow_registry_name: Mapped[str] = mapped_column(String(200))
mlflow_registry_version: Mapped[str] = mapped_column(String(20))  # MLflow devuelve
    # la versión como string numérico (ej. "3"), no como int — se guarda tal cual.
```

Ambos `NOT NULL` porque, tras el punto 1, toda fila `ModelVersion` se crea *después*
de un `register_model` exitoso — no puede existir una fila sin su contraparte en el
Registry. Migración Alembic nueva (`0009_...`, siguiendo la numeración correlativa ya
en uso en `backend/alembic/versions/`), añadiendo ambas columnas a `model_versions`.
Al ser `NOT NULL` sobre una tabla que puede tener filas existentes en un entorno con
datos, la migración debe decidir un valor por defecto para las filas ya existentes
(backfill con `mlflow_registry_name = name` y `mlflow_registry_version = '0'` como
centinela, o dejarlas `NULL`-ables si el equipo prefiere no bloquear el despliegue —
decisión menor de implementación, no de arquitectura).

### 4. Detección y resolución de divergencia

Se añade una función de reconciliación manual (no automática en esta fase, conforme
al criterio de aceptación de la Epic), ej. `model_service.check_registry_divergence(db)`
expuesta como endpoint interno de solo lectura para `MODEL_APPROVER`/`ADMIN`
(`GET /model-versions/registry-divergence`):

- Recorre las `ModelVersion` no soft-eliminadas, consulta
  `MlflowClient().get_model_version(name, version).current_stage` para cada una, y lo
  compara contra el stage esperado según el mapeo del punto 2 aplicado a su `status`
  local.
- Devuelve la lista de discrepancias (`model_version_id`, `status` local, stage
  esperado, stage real en MLflow) — **no corrige nada automáticamente**. Ante una
  divergencia, gana la tabla propia (`status`) como fuente de verdad de negocio — ver
  ADR-2, el flujo de aprobación humana es innegociable — pero corregir el stage de
  MLflow para que vuelva a coincidir es una acción humana explícita (un endpoint
  `POST .../resync` separado, fuera de alcance de esta Epic, se deja como fast-follow
  en `docs/BACKLOG.md`), no algo que la función de detección haga por sí sola.
- Por qué manual y no automático: la causa más probable de divergencia en esta fase es
  un fallo parcial real (ver punto 2) que ya es raro dado el diseño "todo o nada"
  anterior; forzar una resincronización automática sin que un humano la revise
  arriesga enmascarar el motivo real del fallo.

### 5. Impacto en el flujo existente

`review()` y `promote()` **no cambian su firma, sus excepciones
(`MissingJustificationError`, `InvalidModelStateError`) ni la respuesta que exponen los
endpoints de `app/api/v1/models.py`**. La justificación obligatoria y el ciclo
`PENDING_REVIEW → APPROVED/REJECTED → PRODUCTION → RETIRED` no cambian de
comportamiento — las llamadas a MLflow son estrictamente internas, añadidas después de
la lógica ya existente, dentro de la misma función.

### 6. Manejo de errores de conectividad con MLflow en `model_service.py`

`training_service.py` ya establece el patrón: cualquier fallo de MLflow (incluida
conectividad) se trata como fallo del conjunto de la operación, nunca se ignora en
silencio. `model_service.py` sigue el mismo criterio, adaptado a que aquí la operación
es síncrona sobre HTTP, no un job de Celery:

- Se introduce `ModelRegistrySyncError(RuntimeError)` en `model_service.py` (mismo
  patrón que `MissingJustificationError`/`InvalidModelStateError`), que envuelve
  cualquier excepción de `mlflow`/`MlflowClient` al transicionar el stage.
- `review()`/`promote()` la dejan propagar sin capturarla localmente — como solo se ha
  hecho `db.flush()` (nunca `db.commit()`, que es responsabilidad de la ruta, ver
  `app/db/session.py:get_db`), la sesión se cierra sin commitear al elevarse la
  excepción y el cambio de `status` local queda descartado automáticamente: no hace
  falta rollback manual ni lógica de compensación.
- `app/api/v1/models.py` añade `except model_service.ModelRegistrySyncError as exc:
  raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc`
  en `review_model_version`/`promote_model_version` — 502 porque es un fallo de un
  sistema externo (MLflow), no un error de validación del cliente ni de estado del
  dominio.
- Resultado observable: si MLflow no responde durante una aprobación/promoción, la
  petición falla entera con 502 y el estado local **no avanza** — evita exactamente el
  escenario de "aprobado localmente pero divergente en MLflow" que el punto 4 existe
  para poder detectar en los casos que sí se cuelen (ej. MLflow acepta la escritura
  pero la respuesta se pierde por timeout de red).
