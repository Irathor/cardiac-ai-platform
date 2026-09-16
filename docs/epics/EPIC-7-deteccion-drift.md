# EPIC-7: Detección de drift sobre biomarcadores/predicciones

## Historia de usuario
Como ingeniero de ML/MLOps, quiero detectar cuándo la distribución de biomarcadores o
predicciones recientes se desvía del dataset de entrenamiento base, para poder anticipar
degradación del modelo en producción.

## Tipo
Pendiente de decisión (Con IA si se usa una librería como Evidently, Normal si se
implementa un mecanismo estadístico propio).

## Bloqueada por
EPIC-6 (Monitoring básico y métricas de inferencia servida).

## Criterios de aceptación
- [ ] Se compara periódicamente la distribución de features/predicciones recientes contra el
      dataset de entrenamiento base.
- [ ] El resultado de la comparación queda expuesto de alguna forma verificable (métrica,
      reporte, endpoint — a definir junto con el mecanismo elegido).

## Alcance
A definir junto con el mecanismo de drift elegido (`ml/` y/o backend, según se decida).

## Fuera de alcance
Reentrenamiento automático disparado por drift (queda como fast-follow en
`docs/BACKLOG.md`).

## Nota
Requiere decisión previa del usuario sobre el mecanismo de drift (librería tipo Evidently
vs. estadístico propio) antes de poder implementarse — ver Shepard/Liara cuando toque.

## Estado
Propuesta
