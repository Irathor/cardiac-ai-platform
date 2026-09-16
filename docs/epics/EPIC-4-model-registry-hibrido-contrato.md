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
- [ ] Se implementa el modelo híbrido decidido en ADR-2: el Model Registry nativo de MLflow
      es la fuente de verdad del artefacto del modelo y de su stage técnico
      (`Staging`/`Production`/`Archived` o equivalente); la tabla propia
      (`ModelVersion`/`ModelApproval`) sigue siendo la fuente de verdad exclusiva del flujo
      de aprobación humana con justificación obligatoria.
- [ ] Queda definido y documentado el punto exacto de sincronización entre ambos sistemas:
      cuándo se registra un artefacto en el MLflow Registry frente a cuándo se crea la fila
      `ModelVersion` propia.
- [ ] Queda definido y documentado qué ocurre si el stage de MLflow y el `status` propio
      llegan a divergir (detección y resolución, aunque sea manual en esta fase).
- [ ] El flujo de aprobación humano existente (ciclo `PENDING_REVIEW → APPROVED/REJECTED →
      PRODUCTION → RETIRED` con justificación obligatoria) no cambia de comportamiento de cara
      al usuario — solo cambia qué sistema es responsable del artefacto/stage técnico
      subyacente.

## Alcance
`backend/app/models/model_version.py`, `backend/app/models/model_approval.py`,
`backend/app/services/model_service.py`, `backend/app/services/training_service.py`,
integración con el Model Registry nativo de MLflow.

## Fuera de alcance
Cambios en el flujo de aprobación humano con justificación, que se mantiene igual (ver
ADR-2).

## Estado
Propuesta
