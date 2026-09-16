# EPIC-3: Explicabilidad con Grad-CAM integrada en el flujo de análisis servido

## Historia de usuario
Como médico/usuario del portal clínico, quiero que el informe de un análisis de IA real
incluya su mapa de atribución Grad-CAM, para poder ver qué regiones de la imagen influyeron
en la predicción sin depender de un cálculo offline aparte.

## Tipo
Con IA

## Bloqueada por
EPIC-1 (Explicabilidad real — Grad-CAM (U-Net/CNN3D) + panel comparativo LIME vs. Shapley) y
EPIC-2 (Servir los modelos reales (U-Net/CNN3D) desde la API de inferencia) — esta Epic
necesita ambas piezas ya construidas para tener sentido end-to-end.

## Criterios de aceptación
- [ ] El resultado de un `AIAnalysis` real (no solo un cálculo offline) incluye su mapa de
      atribución Grad-CAM, calculado con el módulo de explicabilidad de EPIC-1 sobre el
      modelo servido de EPIC-2.
- [ ] El mapa de atribución es visible como parte del informe del análisis.

## Alcance
Backend (`AIAnalysis`, flujo de `analysis_service.py`/tareas Celery) e integración con el
módulo de explicabilidad de `ml/` construido en EPIC-1.

## Fuera de alcance
- LIME (ver ADR-3 — LIME no forma parte del flujo de producción servido).

## Estado
Propuesta
