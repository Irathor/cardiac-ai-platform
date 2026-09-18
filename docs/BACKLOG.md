# Backlog

Este archivo distingue tres cosas que no son lo mismo (ver `~/.claude/CLAUDE.md`,
"Backlog de fast-follows"): **Fast-follows** (listos para convertirse en Epic),
**Niebla** (dirección conocida, pregunta todavía sin afilar) y **Fuera de alcance**
(descartado deliberadamente, con motivo).

## Fast-follows

- **Migrar secretos de despliegue de Oracle Cloud de `user_data`/cloud-init a OCI Vault** —
  EPIC-8 pasa `postgres_password`/`minio_secret_key`/`jwt_secret_key`/`grafana_admin_password`
  a la instancia vía `user_data` de Terraform (variables `sensitive`, nunca comiteadas), que
  cloud-init escribe en `.env` con `chmod 600`. `security-review` en el cierre de EPIC-8/9
  evaluó esto como riesgo real pero no bloqueante en el contexto actual (instancia personal
  de un solo operador, no multi-tenant, proyecto ya documentado como fuera de alcance clínico
  real) — el `user_data` queda igualmente legible sin autenticación adicional desde el propio
  IMDS de la instancia y vía la consola/API de OCI para quien tenga permisos IAM sobre ella.
  Migrar a OCI Vault (cloud-init lo consulta vía instance principal en vez de recibir el
  secreto ya embebido) sería más correcto si el contexto de confianza cambia (más operadores,
  compartment compartido, identidad de CI con acceso a metadata de instancias).
- **Renderizar el mapa de Grad-CAM en la pantalla de informe del frontend** — ahora es
  [EPIC-14: Explicabilidad visual en el visor de imágenes (Grad-CAM overlay + consistencia de
  biomarcadores CNN3D)](epics/EPIC-14-explicabilidad-visual-en-el-visor.md). Ya no vive como
  fast-follow suelto aquí; el detalle completo (parseo de `.npy` en el cliente, panel
  independiente de slices, tabla de consistencia de biomarcadores) está en esa Epic.
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

[EPIC-8: Deployment cloud](epics/EPIC-8-deployment-cloud.md) y
[EPIC-9: Infrastructure as Code con Terraform](epics/EPIC-9-infrastructure-as-code-terraform.md)
ya no están aquí: la decisión de proveedor (Oracle Cloud real + AWS scaffold, ver
[ADR-6](adr/ADR-6-oracle-cloud-real-aws-scaffold.md)) y las decisiones de Caddy/hostname
`sslip.io` están tomadas y fijadas en ambas Epics — listas para implementar.

El reentrenamiento automático disparado por drift (mencionado como "Fuera de alcance" en
[EPIC-7: Detección de drift sobre biomarcadores/predicciones](epics/EPIC-7-deteccion-drift.md),
ya redactada y lista para implementar tras la decisión de mecanismo del usuario) es una
dirección conocida pero sin forma concreta todavía — no se redacta como fast-follow hasta que
exista un mecanismo de drift real (EPIC-7) sobre el que definir el disparo automático.

## Fuera de alcance

- **Batería ampliada de métricas de validación (robustez sintética, OOD, latencia/throughput,
  subgrupos finos)** — [EPIC-17: Selección de modelo al reentrenamiento + panel de validación
  completo](epics/EPIC-17-seleccion-modelo-reentrenamiento-panel-validacion.md) implementa el
  "conjunto mínimo obligatorio" de métricas que el propio usuario delimitó, no la lista completa
  de 174 métricas que propuso junto a él. Motivo: el propio usuario acotó qué era obligatorio
  para esta iteración; lo no implementado se documenta como tal en la UI, nunca se simula. Queda
  explícitamente fuera: batería de robustez sintética (ruido/rotación/contraste/slices
  faltantes/ficheros corruptos), detección OOD, análisis por subgrupo salvo lo trivialmente
  disponible, métricas de latencia/throughput/hardware. Puede retomarse como iteración 2 si el
  usuario confirma que quiere ampliar el conjunto de métricas.
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
