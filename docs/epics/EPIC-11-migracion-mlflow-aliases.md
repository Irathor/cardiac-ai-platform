# EPIC-11: Migración del Model Registry de stages deprecados a aliases de MLflow

## Historia de usuario
Como ingeniero de ML/MLOps, quiero que la sincronización con el Model Registry de MLflow use
la API moderna de aliases en vez de la API de stages (deprecada desde MLflow 2.9.0), para no
quedar dependiendo de un mecanismo que MLflow puede eliminar en una futura versión mayor.

## Tipo
Normal

## Bloqueada por
EPIC-4 (Contrato y esquema del Model Registry híbrido) y EPIC-5 (CI/CD ampliado — actualización
a mlflow 3.16.1). Ambas ya completadas.

## Corrección post-implementación (hallada por verificación e2e real, no por diseño)

El contrato técnico de Shepard (sección 4, "Qué NO cambia") asumía que reasignar el alias
`production` a la versión nueva "retira automáticamente" el alias de la versión anterior sin
llamada explícita, y que por tanto la segunda mitad de `promote()` (demover la versión
`PRODUCTION` anterior) dejaría de hablar con MLflow de verdad. **Esto resultó ser incorrecto
en la práctica**: `_sync_alias` se invoca una vez por cada `ModelVersion` afectada dentro de
la misma operación de `promote()`, y el `delete_registered_model_alias(name, alias)` que
dispara para la versión demovida **no está scopeado por versión** — borra el alias por
nombre, apunte a quien apunte en ese momento. Con el orden original (asignar `production` a
la nueva versión primero, borrar de la antigua después), el `delete` posterior borraba el
alias que ya se había movido a la versión recién promovida, dejando **ninguna** versión con
`production` en MLflow. Tali lo detectó ejecutando el bucle real contra un servidor MLflow
real (ningún test unitario mockeado lo habría detectado, porque el `status` local seguía
siendo correcto pese a la divergencia real). Corregido invirtiendo el orden en `promote()`:
primero se libera el alias de la versión saliente, después se asigna a la entrante; el
revert best-effort también se invirtió simétricamente. Este es exactamente el tipo de cosa
que la verificación end-to-end real (no solo mocks) de esta Epic existía para atrapar.

## Criterios de aceptación
- [x] `model_service.py` deja de llamar a `MlflowClient().transition_model_version_stage(...)`
      y de leer `registry_version.current_stage`. En su lugar usa
      `MlflowClient().set_registered_model_alias(name, alias, version)` /
      `MlflowClient().delete_registered_model_alias(name, alias)` para escribir, y
      `ModelVersion.aliases` (o `get_model_version_by_alias`) para leer.
- [x] El mapeo `ModelVersionStatus → alias` queda definido explícitamente (reemplaza a
      `_STAGE_BY_STATUS`), documentado en el código y en la sección "Contrato técnico" de esta
      Epic una vez implementado. Punto de partida (a confirmar/ajustar por Shepard/Tali al
      implementar, ver nota más abajo):

      | `ModelVersionStatus` propio | Alias MLflow (minúscula, convención MLflow) |
      |---|---|
      | `PENDING_REVIEW` | Ninguno (sin alias asignado) |
      | `APPROVED`       | `staging` |
      | `PRODUCTION`     | `production` |
      | `REJECTED`       | `archived` |
      | `RETIRED`        | `archived` |

- [x] **Nota abierta para Shepard/Tali, a resolver al implementar** (diferencia real de modelo
      de datos frente a "stage"): un alias en MLflow no es mutuamente excluyente como lo era un
      stage — una misma versión puede tener varios alias a la vez, y un alias puede reasignarse
      libremente de una versión a otra sin que la versión anterior pierda automáticamente los
      demás alias que tuviera. Antes de dar el mapeo por definitivo, decidir y documentar:
      - Si asignar un alias nuevo implica **borrar explícitamente** cualquier alias previo de
        esa misma versión que ya no aplique (p. ej. al pasar de `APPROVED` a `PRODUCTION`, ¿se
        borra el alias `staging` de esa versión, o conviven `staging` y `production` sobre la
        misma versión?). Recomendación: borrar el alias saliente en la misma operación que se
        asigna el entrante, replicando el comportamiento "un estado activo a la vez" que tenía
        `status` localmente — pero es una decisión de Shepard/Tali, no una asunción de esta
        Epic.
      - Cómo se representa `REJECTED`/`RETIRED` compartiendo el alias `archived`: como con
        stages ya compartían `Archived`, no es un cambio de comportamiento, pero confirmar que
        sigue siendo aceptable con aliases (no hay ambigüedad nueva: ambos casos ya perdían la
        distinción al mapear a MLflow).
- [x] `promote()` mantiene el mismo comportamiento observable que documentó EPIC-4: al promover
      una versión a `production`, si existía una versión previa en `production`, esa versión
      pierde el alias `production` (y gana `archived` según el mapeo) en la misma operación —
      y el revert best-effort ya implementado en EPIC-4 (si la segunda transición de MLflow
      falla tras la primera) se adapta al mecanismo de alias sin perder esa protección.
- [x] `review()`/`promote()` mantienen la misma firma, las mismas excepciones
      (`MissingJustificationError`, `InvalidModelStateError`) y el mismo `ModelRegistrySyncError`
      propagado sin capturar en fallo de conectividad con MLflow — el `status` local nunca
      queda persistido (`commit`) si la llamada a MLflow falla, igual que en EPIC-4 (sigue
      bastando con que solo haya `db.flush()` antes de la llamada a MLflow, sin `db.commit()`).
- [x] `check_registry_divergence()` sigue detectando discrepancias, ahora comparando el alias
      esperado (según el mapeo nuevo) contra los alias reales presentes en
      `ModelVersion.aliases` de la versión consultada, en vez de contra `current_stage`.
- [x] El sentinel `mlflow_registry_version="0"` (filas backfilled por la migración `0009` de
      EPIC-4, sin contrapartida real en MLflow) se sigue manejando sin romper el reporte
      completo: un fallo de lectura por fila individual se reporta como una entrada de
      divergencia con `fetch_error` (mismo mecanismo ya introducido en el checkpoint de cierre
      de EPIC-4), nunca aborta `check_registry_divergence()` para el resto de filas.
- [x] Toda la suite de tests de `test_model_api.py` sigue pasando, incluidos los 2 tests de
      regresión del security-review de EPIC-4
      (`test_promote_reverts_the_first_mlflow_transition_when_the_second_fails` y
      `test_registry_divergence_endpoint_reports_an_unreachable_version_without_failing_the_whole_report`)
      — se actualizan para reflejar el mecanismo de alias si su implementación depende
      directamente de `transition_model_version_stage`/`current_stage`, sin perder la cobertura
      equivalente de los dos escenarios que prueban.
- [x] Verificación end-to-end real contra un servidor MLflow real (mismo enfoque que la
      verificación de EPIC-5: venv real, servidor MLflow containerizado real, no mocks), para
      confirmar que `set_registered_model_alias`/`delete_registered_model_alias`/lectura de
      `aliases` funcionan tal como se documenta y sin el `FutureWarning` de deprecación que
      generaba la API de stages.

## Alcance
`backend/app/services/model_service.py`, `backend/app/services/training_service.py` (si
referencia stages en algún punto), `backend/tests/test_model_api.py`.

## Fuera de alcance
Cualquier cambio al ciclo de aprobación humano (`ModelVersionStatus`, justificación obligatoria
en `review()`/`promote()`, RBAC de los endpoints) — eso no cambia, esta Epic migra únicamente
el mecanismo interno de sincronización con el Model Registry de MLflow.

## Contrato técnico (Shepard)

Verificado contra la API real instalada (`backend/.venv`, mlflow 3.16.1):
`ModelVersion.aliases` es `list[str] | None` (no un objeto `RegisteredModelAlias`), y
`FileStore.set_registered_model_alias` implementa el alias como un puntero único
`nombre_alias -> versión` que se **sobrescribe** al reasignarlo — no se acumula. Esto confirma
que dos versiones distintas nunca pueden compartir el mismo nombre de alias a la vez, y que
reasignar un alias a una versión nueva se lo retira automáticamente a quien lo tuviera antes
(sin llamada explícita de borrado). Este comportamiento cambia el mapeo que proponía el
borrador de la Epic, no solo la mecánica de `_transition_stage`.

### 1. Exclusividad de alias — respuesta: (a) con matiz

La regla general es **(a): borrar explícitamente el alias saliente de esa versión concreta
antes/al asignar el entrante**, vía una función `_sync_alias(model_version, previous_status,
new_status)` que sustituye a `_transition_stage`:

```python
old_alias = _ALIAS_BY_STATUS[previous_status]
new_alias = _ALIAS_BY_STATUS[new_status]
if old_alias == new_alias:
    return  # no-op, incluye None -> None
if old_alias is not None:
    client.delete_registered_model_alias(name, old_alias)
if new_alias is not None:
    client.set_registered_model_alias(name, new_alias, version)
```

Esto simula la exclusividad "un estado activo a la vez" que `status` ya asume localmente,
igual que recomendaba la nota de Liara. **Matiz confirmado con la API real**: cuando
`old_alias == new_alias` (el caso especial es `production`, ver más abajo), la reasignación de
MLflow ya retira el alias de la versión anterior como efecto secundario del propio
`set_registered_model_alias` — no hace falta (ni hay que) llamar a
`delete_registered_model_alias` sobre la versión saliente en ese caso, porque el nombre del
alias ya "se ha movido" de una versión a otra. `_sync_alias` no necesita un caso especial para
esto: al comparar `old_alias == new_alias` en cada versión por separado (cada llamada de
`_sync_alias` opera sobre una única `ModelVersion`), el borrado explícito solo se dispara
cuando la versión en cuestión pierde un alias que no va a ser sustituido por otro con el mismo
nombre en esa misma llamada — que es exactamente lo que hace falta.

### 2. Mapeo final `ModelVersionStatus → alias` — ajustado sobre la propuesta de Liara

El borrador original (`staging`/`production`/`archived`) asumía que un alias puede representar
"muchas versiones en el mismo estado a la vez", como sí podía un stage. La API real lo
contradice: un nombre de alias es un puntero único. Y el modelo de datos propio **sí permite**
varias versiones simultáneas en `APPROVED`, `REJECTED` o `RETIRED` (no hay invariante local que
lo impida — `model_repository` solo garantiza unicidad para `PRODUCTION`, vía
`get_production()`). Reutilizar `staging`/`archived` como alias compartido crearía divergencia
perpetua e incorregible para toda versión salvo la más reciente en ese estado (la razón exacta
por la que existe `check_registry_divergence`, contaminada con ruido estructural en vez de
divergencias reales).

Mapeo final:

| `ModelVersionStatus` propio | Alias MLflow |
|---|---|
| `PENDING_REVIEW` | Ninguno |
| `APPROVED`       | Ninguno |
| `PRODUCTION`     | `production` |
| `REJECTED`       | Ninguno |
| `RETIRED`        | Ninguno |

Decisión explícita frente a la pregunta de Liara sobre `PENDING_REVIEW`: **ningún alias
explícito** (ni `pending-review` ni ningún otro), no solo para `PENDING_REVIEW` sino para los
cuatro estados sin invariante de unicidad local. Un alias explícito ahí sería más verificable
en teoría, pero sobre un puntero único no puede representar "N versiones en este estado" sin
mentir sobre cuál de ellas es la vigente — no es trabajo innecesario evitado, es directamente
incorrecto de implementar. `production` es el único alias con semántica real en MLflow porque
es el único estado con invariante de exclusividad ya garantizado localmente
(`model_repository.get_production`), lo que hace seguro y fiel representarlo como puntero
único de MLflow.

**Consecuencia observable que hay que anotar** (cambio de comportamiento real, no solo de
mecanismo): con este mapeo, `review()` en su rama `approve=True` pasa a ser una transición
`None -> None` — ya no llama a MLflow en absoluto (hoy sí transiciona a `Staging`). Solo
`promote()` sigue hablando con MLflow. Esto es una simplificación deseable (menos
acoplamiento, un fallo de MLflow ya no puede bloquear una aprobación), pero cambia qué camino
de código puede lanzar `ModelRegistrySyncError`: antes tanto `review(approve=True)` como
`promote()` podían lanzarlo, ahora solo `promote()`. Los tests que hoy fuerzan un fallo de
MLflow durante `review()` deben moverse/reescribirse contra `promote()` si dependían de esa
ruta.

### 3. `check_registry_divergence`

Usar `ModelVersion.aliases` (atributo real confirmado: `list[str] | None`, no
`RegisteredModelAlias`) en vez de `current_stage`. Comparación exacta por conjunto, no solo
"¿está presente el alias esperado?" — así se detecta también contaminación (un alias que no
debería estar ahí, p. ej. residuo de una migración manual o de un bug):

```python
expected_alias = _ALIAS_BY_STATUS[model_version.status]
expected_aliases = {expected_alias} if expected_alias is not None else set()
actual_aliases = set(registry_version.aliases or [])
if actual_aliases != expected_aliases:
    # divergencia
```

Se mantiene sin cambios el manejo del sentinel `mlflow_registry_version="0"` y de cualquier
fallo de lectura por fila: se captura la excepción de `client.get_model_version(...)`, se
añade una `RegistryDivergence` con `fetch_error` poblado, y se continúa con el resto — nunca se
aborta `check_registry_divergence()` completo por una fila. `RegistryDivergence.expected_stage`
/`actual_stage` se renombran a `expected_alias`/`actual_alias` (o se documenta en el propio
dataclass que ahora representan un alias, no un stage) para no dejar el nombre del campo
mintiendo sobre lo que contiene.

### 4. Qué NO cambia

`ModelRegistrySyncError` (misma clase, mismo criterio de propagación sin capturar, mismo hecho
de que solo hay `db.flush()` antes de la llamada a MLflow — nunca `db.commit()`), la firma de
`review()`/`promote()`, y el revert best-effort de `promote()` (aunque, dado el mapeo nuevo, la
segunda mitad de `promote()` — demover la `PRODUCTION` anterior a `RETIRED` — ya no dispara
ninguna llamada real a MLflow, porque `RETIRED` mapea a `None` y el alias `production` ya se le
ha retirado automáticamente a esa versión como efecto colateral de asignárselo a la nueva
versión. El bloque de revert sigue siendo correcto tenerlo por robustez ante un futuro cambio
de mapeo, pero en la práctica actual ese `try/except ModelRegistrySyncError` alrededor de la
segunda transición queda como código muerto-pero-inofensivo hasta que el mapeo vuelva a tener
un segundo alias real que sincronizar. Documentarlo en el docstring de `promote()` para que no
se lea como una llamada a MLflow que en la práctica nunca ocurre.

## Verificación
- `backend`: 124/124 tests en verde (re-ejecutado de forma independiente por el
  orquestador), `ruff check` limpio. Sin el `FutureWarning` de stages deprecados que
  aparecía antes en la suite — confirma que la migración eliminó el uso de la API vieja.
- Verificación end-to-end real de Tali contra un servidor MLflow real (sqlite-backed,
  puerto 5551): confirmó que reasignar un alias a otra versión lo retira automáticamente de
  la anterior, que borrar un alias inexistente no lanza excepción, y encontró y corrigió el
  bug real de orden en `promote()` documentado arriba en "Corrección post-implementación".
- Sin `security-review` formal: cambio de mecanismo interno puro (sin endpoint nuevo, sin
  cambio de RBAC), confirmado por inspección directa del diff por el orquestador — el único
  cambio de superficie observable es el renombrado de `expected_stage`/`actual_stage` a
  `expected_alias`/`actual_alias` en `ModelRegistryDivergenceOut`, sin consumidores en el
  frontend todavía (verificado, `grep` sin resultados).

## Estado
Completada
