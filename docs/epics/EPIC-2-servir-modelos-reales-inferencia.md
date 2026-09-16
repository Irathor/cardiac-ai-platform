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

## Criterios de aceptación
- [ ] `analysis_service.py` deja de servir siempre el clasificador nearest-centroid: cuando
      el modelo marcado `PRODUCTION` es de tipo `UNET_SEGMENTATION` o `CNN3D_CLASSIFICATION`,
      la inferencia real corre esos pesos entrenados.
- [ ] Queda decidido y documentado si la inferencia servida puede correr en CPU (a
      diferencia del entrenamiento, que requiere GPU según `docs/dl-training-runner.md`) o si
      requiere el mismo runner con GPU.
- [ ] El comportamiento existente (servir el clasificador heurístico cuando el modelo
      `PRODUCTION` es el nearest-centroid) se mantiene sin regresión.

## Alcance
`backend/app/services/analysis_service.py` y la integración con los modelos entrenados de
`ml/`.

## Fuera de alcance
- Entrenamiento de los modelos (ya existe, Fases 7-8).
- El registro de modelos (ya existe; su evolución hacia el híbrido MLflow/tabla propia es
  EPIC-4).

## Estado
Propuesta
