# EPIC-16: Panel de detección de drift en la consola de modelos

## Historia de usuario
Como ingeniero de ML/MLOps, quiero ver el resultado de deriva de biomarcadores/predicciones
de un `ModelVersion` en producción directamente en la consola de entrenamiento, para no tener
que consultar el endpoint de drift a mano ni depender solo de Grafana.

## Tipo
Normal (renderiza el resultado ya calculado por `GET /model-versions/{id}/drift` de EPIC-7;
no se calcula ni se interpreta nada nuevo del lado del cliente).

## Bloqueada por
EPIC-7 (Detección de drift sobre biomarcadores/predicciones) — completada; esta Epic solo
consume su endpoint ya existente.

## Criterios de aceptación
- [x] En `ModelTrainingPage`, cuando el `ModelVersion` seleccionado tiene `status ===
      "PRODUCTION"`, aparece una pestaña adicional "Drift" (junto a Summary/Classification/
      Validation, etc.) que llama a `GET /model-versions/{id}/drift` y muestra su resultado.
- [x] Cuando el `ModelVersion` seleccionado **no** está en `PRODUCTION`, la pestaña "Drift" no
      aparece (evita mostrar el 409 del backend como si fuera un error real — se refleja el
      mismo criterio que ya aplica el backend: la deriva solo está bien definida para el
      modelo en producción).
- [x] Se muestra, por biomarcador: nombre, estadístico KS, p-value, tamaños de muestra base/
      reciente, umbral (`p < 0.05`) y si se marcó "drift detectado" — como tabla, mismo patrón
      visual que las tablas de métricas ya existentes en `ClassificationTab`/`ValidationTab`.
      Los biomarcadores con `skipped_reason` se muestran con su motivo explícito, no ocultos
      ni como fila vacía.
- [x] Si `biomarkers_skipped_reason` está presente a nivel de reporte (modelo DL sin
      `DatasetVersion`, ver EPIC-7 punto 1), se muestra ese motivo en vez de una tabla vacía.
- [x] Se muestra el resultado de deriva de predicción: PSI, severidad (`NONE`/`MODERATE`/
      `SIGNIFICANT`), tamaños de muestra, con color acorde a la severidad (mismo criterio de
      colores ya usado en el resto de la app: éxito/neutral para `NONE`, advertencia para
      `MODERATE`, error para `SIGNIFICANT` — no se inventa una paleta nueva).
- [x] La pestaña deja claro que esto es una inspección puntual bajo demanda (recalculada solo
      al abrir la pestaña, con caché de 5 minutos en el backend — ver EPIC-7 punto 5), no un
      monitor en vivo — sin barra de progreso ni animación de "streaming".

## Alcance
Frontend únicamente: `frontend/src/pages/ModelTrainingPage.tsx`, nuevo componente
`frontend/src/components/training/DriftTab.tsx`, nuevas funciones/tipos en
`frontend/src/api/training.ts` (o un `frontend/src/api/models.ts` nuevo, a criterio de
Miranda).

## Fuera de alcance
- Cualquier cambio de backend — el endpoint `GET /model-versions/{id}/drift` y su forma
  (`ModelDriftOut`/`BiomarkerDriftOut`/`PredictionDriftOut`) ya existen tal cual desde EPIC-7.
- Panel nuevo de Grafana para los gauges de drift — EPIC-7 ya lo dejó como opción/fast-follow
  a criterio de Liara, independiente de esta Epic (esto es la consola propia de la app, no
  el dashboard de Grafana).
- Disparo de alertas o reentrenamiento automático por drift — fuera de alcance también en
  EPIC-7, sigue sin implementarse aquí.

## Verificación
- `npm run lint`/`build`/`vitest run` (40/40, incluidos los 7 tests nuevos de `DriftTab`):
  re-ejecutados de forma independiente, en verde.
- `security-review` (skill del orquestador, combinado con EPIC-14/15): sin hallazgos — EPIC-16
  no añade endpoints backend nuevos, solo consume `GET /model-versions/{id}/drift` ya
  expuesto y revisado en EPIC-7.
- Verificación visual pendiente de datos reales de drift (requiere un `ModelVersion`
  `PRODUCTION` con historial suficiente) — el componente reutiliza el mismo patrón de tabla
  ya verificado visualmente en `ClassificationTab` (EPIC-13), sin introducir layout nuevo.

## Estado
Completada

## Contrato técnico (Shepard)

### 1. Dónde encaja — pestaña nueva, no página nueva
`ModelTrainingPage.tsx` ya tiene un sistema de tabs por tipo de modelo (`tabsForModel`,
`frontend/src/components/training/*Tab.tsx`) sobre el `ModelVersion` seleccionado en el panel
de "History" — es el sitio natural para el drift, en vez de una página nueva, porque ya es
donde un ingeniero de ML inspecciona el estado de un modelo concreto. A diferencia de las
demás pestañas (que dependen de `selectedEvaluation`, un `ModelEvaluationOut` fijo generado
en el momento del entrenamiento), "Drift" depende solo de `selectedModelVersion.status ===
"PRODUCTION"` y se calcula bajo demanda contra datos recientes — se añade como una condición
extra en `tabsForModel` (o una función `driftTabAvailable(version)` separada que
`ModelTrainingPage` combina con el resultado de `tabsForModel`), visible para **cualquier**
tipo de modelo que esté en `PRODUCTION` (nearest-centroid, U-Net o CNN3D — el backend ya
decide caso a caso si hay biomarcadores o solo predicción, ver EPIC-7 punto 1), no solo para
CNN3D.

### 2. Consumo del endpoint — nueva query, sin re-fetch en cada render
Nueva función `getModelVersionDrift(modelVersionId: string, token: string): Promise<ModelDriftReport>`
en el cliente API (mismo patrón que `listModelEvaluations`), con tipos TS que reflejan
`ModelDriftOut`/`BiomarkerDriftOut`/`PredictionDriftOut` del backend (`biomarker_name`,
`ks_statistic`, `p_value`, `base_sample_size`, `recent_sample_size`, `drift_detected`,
`skipped_reason` por biomarcador; `psi`, `severity`, `drift_detected`, `skipped_reason` para
predicción). Se consulta con `useQuery` (`queryKey: ["model-drift", selectedModelVersionId,
token]`, `enabled: !!token && !!selectedModelVersionId && selectedModelVersion?.status ===
"PRODUCTION"`), **sin** `refetchInterval` — el backend ya cachea 300s (EPIC-7 punto 5) y esto
es una inspección bajo demanda, no un stream; refrescar solo al reabrir la pestaña o con un
botón explícito "Recalcular" es suficiente y evita presionar el endpoint sin necesidad.

### 3. Manejo del 409 sin ensuciar la UI
Aunque el criterio de aceptación ya evita mostrar la pestaña quien no está en `PRODUCTION`,
si por una condición de carrera el estado cambia entre que se listó la versión y se abrió la
pestaña, un 409 se trata igual que cualquier otro error de `useQuery` (`Alert
severity="info"` con el mensaje del backend, no un error rojo alarmante — un modelo que deja
de estar en producción no es una falla del sistema).

### 4. Colores — reutilizar tokens existentes, no inventar
Severidad de PSI: `NONE` → `chartColors`/paleta neutral (mismo gris/verde ya usado para
estados "sin problema" en `RUN_STATUS_COLOR`), `MODERATE` → `warning` (MUI `warning.main`,
ya en el tema), `SIGNIFICANT` → `error` (MUI `error.main`). `drift_detected=true` por
biomarcador (KS) se resalta igual que `SIGNIFICANT` (rojo/ámbar), sin introducir una escala
de color nueva fuera de la paleta de `theme.ts`.

### 5. División de trabajo
Toda la Epic es de **Miranda** (frontend). No requiere a Tali, EDI ni Garrus.

### 6. Seguridad
No aplica `security-review`: sin endpoint nuevo, sin dato nuevo expuesto — el endpoint ya
fue auditado en el cierre de EPIC-7 y esta Epic solo lo consume desde una pantalla ya
protegida por el mismo login/roles que el resto de `ModelTrainingPage`.
