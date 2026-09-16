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
- [x] Grad-CAM real calculado sobre el U-Net entrenado (`data/models/unet2d.pt`) para al
      menos un caso de segmentación real, mostrando qué regiones de la imagen influyeron en
      la predicción de cada estructura (VI/VD/miocardio). Verificado ejecutando
      `ml/scripts/run_explainability_showcase.py` contra el checkpoint real y un paciente
      real de test (`patient101`); resultado guardado en
      `data/models/explainability/explainability_showcase.json` +
      `unet_gradcam_patient101_{LV,RV,MYO}.png`.
- [x] Grad-CAM real calculado sobre el CNN3D entrenado (`data/models/cnn3d/cnn3d.pt`) para
      al menos un caso de clasificación real. Verificado con el mismo script/paciente;
      resultado en `cnn3d_gradcam_patient101_z6.png` (predicción correcta:
      DILATED_CARDIOMYOPATHY).
- [x] Ambos cálculos de Grad-CAM son genuinos sobre las activaciones reales de las capas
      convolucionales de los modelos ya entrenados — nunca una aproximación visual fabricada,
      coherente con la ética de "no inventarnos nada" que ya sigue este proyecto (ver
      `README.md` y `docs/clinical-limitations.md`). Implementado con hooks reales de
      PyTorch (`register_forward_hook`/`register_full_backward_hook`) sobre capas
      intermedias verificadas por inspección directa del modelo (ver
      `ml/cardiac_ai_ml/dl/explainability.py`), Seg-Grad-CAM (Vinogradova et al. 2020) para
      el U-Net y Grad-CAM 3D clásico para el CNN3D.
- [x] Panel comparativo LIME vs. Shapley exacto sobre el clasificador nearest-centroid de
      biomarcadores (`ml/cardiac_ai_ml/classification.py`), con ambos resultados calculados
      de verdad (LIME no simulado) y etiquetado claramente como comparación pedagógica, no
      como explicación de producción (ver ADR-3). Implementado en
      `ml/cardiac_ai_ml/dl/lime_shapley_panel.py`, etiquetas explícitas `"LIME
      (aproximado)"` / `"Shapley (exacto)"`, verificado con datos reales de ACDC en el
      script offline.
- [x] Tests reales (no solo smoke tests triviales) que verifiquen que los mapas de Grad-CAM
      cambian de forma sensata ante entradas distintas — como mínimo, un test tipo
      property-based en el que dos entradas muy distintas produzcan mapas de atribución
      distintos. Ver `ml/tests/dl/test_explainability.py` (property-based +
      class-discriminative, U-Net y CNN3D) y `ml/tests/dl/test_lime_shapley_panel.py`
      (acuerdo de signo LIME/Shapley, etiquetado, coincidencia exacta con
      `explain_with_prototypes`). Suite completa verificada: 159 tests en `.venv-dl`, 31 en
      `.venv` ligero (sigue saltando `tests/dl/*` correctamente), `ruff check` limpio.

## Alcance
Paquete `ml/` (nuevo módulo de explicabilidad para imagen — el nombre exacto lo decide EDI
al implementar, p. ej. `ml/cardiac_ai_ml/dl/explainability.py` o similar) y el panel
LIME/Shapley sobre `ml/cardiac_ai_ml/classification.py`.

**Pregunta abierta resuelta al empezar la implementación**: mecanismo de exposición = script
offline en `ml/scripts/run_explainability_showcase.py`, no endpoint de API — EPIC-3 es
explícitamente el paso que lo conecta a la API real, y depende de EPIC-2 (servir los modelos
reales), que todavía no existe.

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
Completada
