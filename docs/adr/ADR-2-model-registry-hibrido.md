# ADR-2: Model Registry híbrido (MLflow + tabla propia)

## Estado
Aceptada

## Contexto
Una auditoría del código existente (realizada por Shepard) confirma que ya existe un
registro de modelos propio: `backend/app/models/model_version.py`,
`backend/app/models/model_approval.py` y `backend/app/services/model_service.py`
implementan un ciclo de vida `PENDING_REVIEW → APPROVED/REJECTED → PRODUCTION → RETIRED`
con justificación humana obligatoria en cada aprobación y promoción.

MLflow (`backend/app/services/training_service.py`, `infrastructure/mlflow/`) está presente
en el stack desde la Fase 1, pero hasta ahora **solo se usa como tracking de runs**
(parámetros, métricas, artefactos de entrenamiento) — nunca se ha usado su Model Registry
nativo (`mlflow.register_model` / `MlflowClient.transition_model_version_stage`).

Se valoraron tres opciones:
1. Mantener el registro propio como único sistema, sin usar el Model Registry nativo de
   MLflow en absoluto.
2. Migrar todo el ciclo de vida del modelo a MLflow puro (usando sus stages nativos
   `Staging`/`Production`/`Archived`).
3. Un modelo híbrido explícito: MLflow Registry como fuente de verdad del artefacto/stage,
   tabla propia como fuente de verdad del flujo de aprobación humana.

La opción 1 pierde la trazabilidad estándar de MLflow (versionado de artefactos, lineage de
runs, integración con las herramientas del ecosistema MLflow) sin ninguna ganancia a cambio.
La opción 2 pierde la justificación humana obligatoria en cada aprobación/promoción, que es
un requisito propio de este proyecto y que MLflow no modela de forma nativa (sus stages no
tienen un campo de justificación textual obligatoria asociado a la transición).

## Decisión
Se adopta el modelo **híbrido explícito** (opción 3), elegido por el usuario:

- El **Model Registry nativo de MLflow** pasa a ser la fuente de verdad del artefacto del
  modelo y de su stage técnico (equivalente a `Staging`/`Production` de MLflow).
- La **tabla propia** (`ModelVersion`/`ModelApproval`) se mantiene, exclusivamente, como la
  fuente de verdad del flujo de aprobación humana con justificación obligatoria — el ciclo
  `PENDING_REVIEW → APPROVED/REJECTED → PRODUCTION → RETIRED` no desaparece ni se sustituye.

Este ADR fija la decisión de diseño (qué sistema es dueño de qué). El punto exacto de
sincronización entre ambos — cuándo se registra un artefacto en el MLflow Registry frente a
cuándo se crea la fila `ModelVersion` propia, y cómo se resuelve si un stage de MLflow y el
`status` propio llegan a divergir — es un detalle de implementación que se define en
EPIC-4 (Contrato y esquema del Model Registry), no en este ADR.

## Consecuencias
- Dos sistemas deben mantenerse consistentes entre sí (deuda de sincronización): cualquier
  cambio de stage debe reflejarse en ambos sistemas, o el equipo debe decidir en EPIC-4 cuál
  de los dos dispara al otro.
- Se gana trazabilidad estándar de MLflow (versionado de artefactos, lineage completo desde
  el run de entrenamiento) sin perder el requisito de justificación humana obligatoria que
  ya diferencia a este proyecto de un registro MLflow "de manual".
- El flujo de aprobación humano existente (`model_service.py`, endpoints de aprobación) no
  cambia de comportamiento con este ADR — solo cambia qué sistema es responsable del
  artefacto/stage técnico subyacente.
