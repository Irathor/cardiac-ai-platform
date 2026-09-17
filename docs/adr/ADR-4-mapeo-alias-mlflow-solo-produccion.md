# ADR-4: Mapeo de `ModelVersionStatus` a aliases de MLflow — solo `PRODUCTION`

## Estado
Aceptada

## Contexto
EPIC-11 (Migración del Model Registry de stages deprecados a aliases de MLflow) partía de un
mapeo borrador `PENDING_REVIEW → ninguno / APPROVED → staging / PRODUCTION → production /
REJECTED, RETIRED → archived`, pensado como equivalente directo de los stages de MLflow que
sustituye (`Staging`/`Production`/`Archived`).

Shepard verificó ese borrador contra la API real instalada (`backend/.venv`, mlflow 3.16.1) y
encontró que la premisa no se sostiene: un **alias** de MLflow (`ModelVersion.aliases`,
`MlflowClient.set_registered_model_alias`) es un puntero único `nombre_alias -> versión` que se
**sobrescribe** al reasignarse — nunca puede apuntar a varias versiones de un mismo modelo a la
vez. Un **stage**, en cambio, sí admitía varias versiones simultáneas en el mismo stage. El
modelo de datos propio (`ModelVersion.status`, `model_repository`) permite varias filas
simultáneas en `APPROVED`, `REJECTED` o `RETIRED` para el mismo `name` de modelo — no hay ninguna
restricción de unicidad local para esos tres estados. La única unicidad garantizada localmente es
la de `PRODUCTION`, vía `model_repository.get_production()`.

Reutilizar un alias compartido (`staging` para todo `APPROVED`, `archived` para
`REJECTED`+`RETIRED`) sobre un puntero de versión única produciría divergencia perpetua e
incorregible para toda versión salvo la más reciente en ese estado: `check_registry_divergence()`
reportaría contaminación estructural constante en vez de divergencias reales, defeando el
propósito de esa función.

Se valoraron dos opciones:
1. **Mantener el mapeo original con un alias "casi único" por grupo** (p. ej. sufijar el alias
   con el id de versión, o aceptar la sobrescritura como comportamiento esperado). Descartada:
   añade complejidad de implementación (generar/parsear nombres de alias dinámicos, o vivir con
   que el alias de `staging`/`archived` mienta sobre cuál versión representa) sin ningún
   beneficio real — nada en el proyecto necesita consultar desde MLflow "qué versiones están en
   revisión/rechazadas/retiradas"; esa pregunta ya la responde la tabla propia
   (`ModelVersion.status`), que es la fuente de verdad del flujo de aprobación humana desde
   ADR-2.
2. **Solo `PRODUCTION` tiene alias real en MLflow** (`production`); los demás estados no
   asignan ningún alias. Elegida.

## Decisión
Se adopta el mapeo `ModelVersionStatus → alias de MLflow` reducido a un único caso real:

| `ModelVersionStatus` propio | Alias MLflow |
|---|---|
| `PENDING_REVIEW` | Ninguno |
| `APPROVED`       | Ninguno |
| `PRODUCTION`     | `production` |
| `REJECTED`       | Ninguno |
| `RETIRED`        | Ninguno |

`production` es el único alias con semántica real porque es el único estado con invariante de
exclusividad ya garantizado localmente (`model_repository.get_production()`), lo que permite
representarlo con fidelidad como puntero único de MLflow. Los demás estados no tienen invariante
de unicidad local, así que un alias único sobre ellos no puede representarlos sin mentir sobre
cuál versión es "la" vigente en ese estado — no es una simplificación por pereza, es lo único
correcto de implementar dado que un alias no admite "N versiones en este estado" como sí admitía
un stage.

Consecuencia directa en el código: `_sync_alias()` sustituye a `_transition_stage()` y solo se
invoca desde `promote()`. `review()` (tanto en su rama `approve=True` como `approve=False`) deja
de llamar a MLflow — con stages, `APPROVED` transicionaba a `Staging` y `REJECTED` a `Archived`;
con aliases, ambas transiciones son `None -> None`, un no-op.

## Consecuencias
- **`review()` deja de sincronizar con MLflow.** Esto es un cambio de comportamiento interno
  observable en tests (los que hoy fuerzan un fallo de MLflow durante `review()` para comprobar
  que `ModelRegistrySyncError` se propaga y el `status` no se persiste deben moverse/reescribirse
  contra `promote()`, que es la única operación que sigue pudiendo lanzar ese error), no en la
  API pública (`review()` mantiene su firma y sus excepciones propias,
  `MissingJustificationError`/`InvalidModelStateError`).
- **Ventaja real, no solo una limitación aceptada**: reduce la superficie de fallo de MLflow en
  el camino de aprobación humana. Antes, un MLflow inalcanzable podía bloquear una aprobación o
  un rechazo (`review()` propagaba `ModelRegistrySyncError` si la transición de stage fallaba);
  ahora ese camino es puramente local y solo `promote()` — la operación que de verdad necesita
  hablar con el Model Registry — puede fallar por causa de MLflow.
- El bloque de revert best-effort de `promote()` (demover la `PRODUCTION` anterior tras un fallo
  en la segunda mitad de la operación) queda como código muerto-pero-inofensivo en la práctica
  actual: al mapear `RETIRED → None`, la "democión" de la versión saliente ya no dispara ninguna
  llamada real a MLflow (el alias `production` ya se le retiró automáticamente como efecto
  colateral de asignárselo a la versión entrante). Se conserva por robustez ante un futuro cambio
  de mapeo, documentado en el docstring de `promote()` para que no se lea como una llamada a
  MLflow que en la práctica nunca ocurre.
- `check_registry_divergence()` pasa a comparar por conjunto (`ModelVersion.aliases` frente al
  alias esperado, que es `{"production"}` o el conjunto vacío) en vez de contra `current_stage`,
  lo que además detecta contaminación (un alias presente que no debería estarlo), no solo
  ausencia del esperado.
- Si en el futuro se necesitara consultar desde MLflow "qué versiones están en un estado
  intermedio" (hoy resuelto solo por la tabla propia), este ADR quedaría reemplazado por uno
  nuevo que introduzca un mecanismo distinto (p. ej. tags de MLflow en vez de alias, que sí
  admiten múltiples valores) — no se reabre extendiendo el mapeo de alias actual.
