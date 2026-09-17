# Backlog

Este archivo distingue tres cosas que no son lo mismo (ver `~/.claude/CLAUDE.md`,
"Backlog de fast-follows"): **Fast-follows** (listos para convertirse en Epic),
**Niebla** (dirección conocida, pregunta todavía sin afilar) y **Fuera de alcance**
(descartado deliberadamente, con motivo).

## Fast-follows

- **Renderizar el mapa de Grad-CAM en la pantalla de informe del frontend** — EPIC-3 ya
  expone el dato real y completo vía `GET /analyses/{analysis_id}/gradcam` (array `.npy`,
  mismo RBAC que el resto del análisis); falta la parte visual (overlay/heatmap sobre la
  imagen en `ImagingViewerPage`/donde corresponda). Motivo por el que no entró en EPIC-3: el
  contrato técnico de Shepard decidió que el criterio "visible en el informe" queda
  satisfecho por la exposición de datos vía API (mismo patrón que `features`/
  `probabilities`, que tampoco se renderizan server-side), dejando el render explícitamente
  para un fast-follow — no forma parte del alcance de esta Epic ni de EPIC-10 (rediseño
  visual), que fue sobre el frontend ya existente, no sobre features nuevas.
- **Corrección automática/asistida de divergencias del Model Registry** — EPIC-4 solo
  implementó la detección de solo lectura (`GET /api/v1/model-versions/registry-divergence`,
  ver ADR-2/EPIC-4 "Contrato técnico"). Resolver una divergencia real detectada (decidir si
  se fuerza el stage de MLflow a lo que dice el `status` local, o viceversa) queda como
  acción humana explícita fuera de esta Epic — la tabla propia es la fuente de verdad de
  negocio, así que la corrección por defecto sería "MLflow sigue a la tabla propia", pero no
  se implementó porque el propio criterio de aceptación de EPIC-4 solo pedía detección
  ("aunque sea manual en esta fase").
- **Migrar `model_service.py`/`training_service.py` de los "stages" deprecados de MLflow** —
  convertido en [EPIC-11: Migración del Model Registry de stages deprecados a aliases de
  MLflow](epics/EPIC-11-migracion-mlflow-aliases.md) a petición explícita del usuario tras
  cerrar EPIC-5. Ya no vive como fast-follow suelto aquí; el detalle completo (mapeo
  `ModelVersionStatus → alias`, manejo de la divergencia real de modelo de datos frente a
  "stage", verificación end-to-end) está en esa Epic.

## Niebla — Epics pendientes de decisión previa

Estas Epics ya están redactadas como ficheros (roadmap completo, propuesto por Shepard),
pero no pueden empezar a implementarse hasta que el usuario tome una decisión concreta que
todavía no se ha pedido. No se fuerza su implementación por rellenar el hueco.

- [EPIC-6: Monitoring básico y métricas de inferencia servida](epics/EPIC-6-monitoring-basico.md)
  — requiere decidir el stack de monitoring (endpoint `/metrics` propio vs.
  Prometheus+Grafana).
- [EPIC-7: Detección de drift sobre biomarcadores/predicciones](epics/EPIC-7-deteccion-drift.md)
  — requiere decidir el mecanismo de drift (librería tipo Evidently vs. estadístico propio).
- [EPIC-8: Deployment cloud](epics/EPIC-8-deployment-cloud.md) — requiere decidir el
  proveedor cloud.
- [EPIC-9: Infrastructure as Code con Terraform](epics/EPIC-9-infrastructure-as-code-terraform.md)
  — depende de la decisión de proveedor cloud de EPIC-8.

Además, el reentrenamiento automático disparado por drift (mencionado como "Fuera de
alcance" en EPIC-7) es una dirección conocida pero sin forma concreta todavía — no se
redacta como fast-follow hasta que exista un mecanismo de drift real (EPIC-7) sobre el que
definir el disparo automático.

## Fuera de alcance

- **LIME sobre imágenes (CNN3D/U-Net) como complemento de Grad-CAM** — descartado en
  [ADR-3](adr/ADR-3-lime-panel-pedagogico.md). Motivo: Grad-CAM ya cubre la explicabilidad
  de imagen en esta fase del roadmap y no se ha identificado qué aportaría LIME sobre
  imágenes que Grad-CAM no cubra ya. Puede volver a proponerse si en el futuro se identifica
  un caso concreto que Grad-CAM no resuelva — no se asume en silencio, el usuario debe
  confirmar que el contexto cambió.
- **HTTPS forzado, observabilidad real (trazas/alertas) y gestión de secretos avanzada
  (vault/secret manager)** — no forman parte de EPIC-8 (Deployment cloud). Motivo: son
  parte de la checklist "Antes de un despliegue de producción real" de las convenciones del
  equipo (`~/.claude/CLAUDE.md`), que se activa explícitamente cuando el usuario indica que
  el despliegue real está cerca, no antes.
- **Migración retroactiva del changelog de fases (Fases 1-8) a formato Epic** — descartado
  en [ADR-1](adr/ADR-1-adopcion-proceso-epics-adr.md). Motivo: el trabajo ya está cerrado,
  verificado y documentado con suficiente detalle en el `README.md`/`docs/phases.md`; no
  aporta valor reescribirlo.
