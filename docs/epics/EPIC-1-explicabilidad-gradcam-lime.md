# EPIC-1: Explicabilidad real — Grad-CAM (U-Net/CNN3D) + panel comparativo LIME vs. Shapley (biomarcadores)

## Historia de usuario
Como ingeniero de ML que presenta este proyecto como portfolio, quiero explicabilidad real y
verificable sobre los modelos de imagen (no solo sobre el clasificador tabular) para poder
mostrar el sistema completo MRI → segmentación → biomarcadores → clasificación →
explicabilidad → informe con evidencia real, no simulada.

## Tipo
Con IA

## Bloqueada por
Ninguna

## Criterios de aceptación
- [ ] Grad-CAM real calculado sobre el U-Net entrenado (`data/models/unet2d.pt`) para al
      menos un caso de segmentación real, mostrando qué regiones de la imagen influyeron en
      la predicción de cada estructura (VI/VD/miocardio).
- [ ] Grad-CAM real calculado sobre el CNN3D entrenado (`data/models/cnn3d/cnn3d.pt`) para
      al menos un caso de clasificación real.
- [ ] Ambos cálculos de Grad-CAM son genuinos sobre las activaciones reales de las capas
      convolucionales de los modelos ya entrenados — nunca una aproximación visual fabricada,
      coherente con la ética de "no inventarnos nada" que ya sigue este proyecto (ver
      `README.md` y `docs/clinical-limitations.md`).
- [ ] Panel comparativo LIME vs. Shapley exacto sobre el clasificador nearest-centroid de
      biomarcadores (`ml/cardiac_ai_ml/classification.py`), con ambos resultados calculados
      de verdad (LIME no simulado) y etiquetado claramente como comparación pedagógica, no
      como explicación de producción (ver ADR-3).
- [ ] Tests reales (no solo smoke tests triviales) que verifiquen que los mapas de Grad-CAM
      cambian de forma sensata ante entradas distintas — como mínimo, un test tipo
      property-based en el que dos entradas muy distintas produzcan mapas de atribución
      distintos.

## Alcance
Paquete `ml/` (nuevo módulo de explicabilidad para imagen — el nombre exacto lo decide EDI
al implementar, p. ej. `ml/cardiac_ai_ml/dl/explainability.py` o similar) y el panel
LIME/Shapley sobre `ml/cardiac_ai_ml/classification.py`.

**Pregunta abierta para el inicio de la implementación** (no resuelta en esta Epic, se
decide con Tali/EDI al empezar): mecanismo de exposición de los resultados de Grad-CAM y del
panel LIME/Shapley — ¿endpoint API nuevo, script/notebook offline, o ambos? Esta Epic no
prejuzga la respuesta.

## Fuera de alcance
- Servir esta explicabilidad desde la API de inferencia en tiempo real como parte del
  informe de un `AIAnalysis` real — eso es EPIC-3 (Explicabilidad con Grad-CAM integrada en
  el flujo de análisis servido), bloqueada por esta Epic y por EPIC-2 (Servir los modelos
  reales desde la API de inferencia).
- LIME sobre imágenes (CNN3D/U-Net) — descartado explícitamente en ADR-3, registrado en
  `docs/BACKLOG.md` como fuera de alcance.
- Cualquier cambio al frontend — lo lleva un agente de frontend aparte con guía visual
  propia; no forma parte de esta Epic.

## Estado
Propuesta
