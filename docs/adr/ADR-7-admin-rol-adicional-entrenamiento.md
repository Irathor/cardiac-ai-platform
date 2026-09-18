# ADR-7: ADMIN como rol adicional en los endpoints de entrenamiento y lectura de model-versions

## Estado
Aceptada

## Contexto
La matriz de permisos original (`docs/permissions.md`) reservaba "Configurar/iniciar/cancelar/
supervisar training runs" y "Ver métricas/artefactos/logs" exclusivamente a `ML_ENGINEER` (y
`MODEL_APPROVER` para la lectura de evaluaciones), con una nota explícita "ADMIN cannot trigger
training" como parte de la separación deliberada entre administración de cuentas/sistema y flujo
clínico/ML.

En [EPIC-17: Selección de modelo al reentrenamiento + panel de validación completo](
../epics/EPIC-17-seleccion-modelo-reentrenamiento-panel-validacion.md), el usuario pidió
explícitamente poder elegir el modelo a reentrenar y ver el panel de validación completo desde
una cuenta `ADMIN`, sin necesitar una cuenta `ML_ENGINEER` separada para esa tarea. Esto es una
desviación real de la regla anterior, no un detalle de implementación — se documenta como
decisión de seguridad en vez de cambiarla en silencio.

Opciones valoradas:
1. **Mantener la restricción y pedir al usuario que use una cuenta `ML_ENGINEER`.** Descartado:
   contradice la petición explícita del usuario, que es quien define el alcance de acceso de su
   propio panel de administración.
2. **Sustituir `ML_ENGINEER` por `ADMIN`** en esos endpoints. Descartado: `ML_ENGINEER` sigue
   siendo el rol operativo normal para esta tarea (crea datasets, compara modelos); quitárselo
   rompería el flujo existente sin necesidad.
3. **Añadir `ADMIN` como rol adicional**, manteniendo `ML_ENGINEER` intacto y sin tocar el resto
   de la separación ADMIN/clínico/ML (ADMIN sigue sin poder aprobar/promover/retirar un modelo,
   eso sigue siendo `MODEL_APPROVER`-only). Elegida.

## Decisión
Se añade `RoleName.ADMIN` junto a `RoleName.ML_ENGINEER` en `require_roles(...)` de:
- `POST /datasets/{id}/versions/{id}/training-runs`
- `GET /datasets/{id}/versions/{id}/training-runs`
- `GET /training-runs/{id}`
- `GET /model-versions*` (lectura de `model-versions`/evaluaciones)

`ADMIN` puede así elegir `model_type` y disparar/leer cualquier training run (nearest-centroid,
U-Net, CNN3D) y ver el panel de validación completo. `ADMIN` **no** gana ningún permiso sobre
activación/aprobación/promoción/retirada de modelos — eso permanece exclusivo de
`MODEL_APPROVER`, sin excepción para cuentas `ADMIN`, igual que ya ocurría con la activación de
modelos.

`docs/permissions.md` se actualiza en el mismo cambio: la tabla marca `ADMIN` también en las
filas de "Configurar/start/cancel/supervise training runs" y "View metrics, artifacts, logs", y
la sección "Explicit denials" documenta explícitamente el motivo y el límite exacto de este
acceso ampliado (para que no se lea como una relajación general de la separación ADMIN/ML).

## Consecuencias
- **Ventaja**: el usuario puede operar el panel de reentrenamiento/validación completo desde su
  propia cuenta `ADMIN`, sin necesitar gestionar una cuenta `ML_ENGINEER` aparte solo para esto.
- **Desventaja/deuda asumida**: la separación de responsabilidades entre administración de
  sistema y operación de ML se vuelve más porosa en este punto concreto. Se acota
  deliberadamente (solo entrenar/leer, nunca aprobar/promover/retirar) para minimizar el riesgo;
  si en el futuro se necesita una separación más estricta (p. ej. multi-tenant con varios
  administradores no confiables entre sí), este ADR queda como referencia de qué se relajó y
  por qué, y tendría que revisarse.
- **Impacto en otros módulos**: ninguno fuera de los endpoints listados — `MODEL_APPROVER` y el
  resto de la matriz de permisos no cambian. Cubierto por `backend/tests/test_training_api.py`
  (ADMIN puede disparar/leer, sigue sin poder aprobar/promover).
