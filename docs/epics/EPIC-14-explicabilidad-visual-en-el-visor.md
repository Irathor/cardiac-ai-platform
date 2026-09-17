# EPIC-14: Explicabilidad visual en el visor de imágenes (Grad-CAM overlay + consistencia de biomarcadores CNN3D)

## Historia de usuario
Como médico/usuario del portal clínico, quiero ver el mapa de atribución Grad-CAM y la señal
de consistencia de biomarcadores de un análisis CNN3D directamente en la pantalla del visor,
sin depender de leer el JSON crudo de la API, para poder interpretar visualmente por qué el
modelo predijo lo que predijo y si es coherente con los biomarcadores reales del caso.

## Tipo
Normal (renderiza datos ya calculados y ya expuestos por el backend en EPIC-3 y EPIC-12; no
se entrena, generaliza ni calcula nada nuevo — es presentación, no un modelo nuevo).

## Bloqueada por
EPIC-3 (Explicabilidad con Grad-CAM integrada en el flujo de análisis servido) y EPIC-12
(Señal de consistencia indirecta para CNN3D vía biomarcadores auto-segmentados) — ambas
completadas; esta Epic solo consume lo que ya exponen.

## Criterios de aceptación
- [x] En `ImagingViewerPage`, cuando el `AIAnalysis` activo es `COMPLETED` y
      `gradcam_available === true`, aparece un control ("Mostrar Grad-CAM") que descarga
      `GET /analyses/{id}/gradcam` y renderiza el array de atribución como un panel de
      slices con mapa de calor (colormap tipo "jet"), navegable por un slider de slice
      independiente del `NiftiViewer`, con una nota visible explicando que el mapa vive en
      el espacio de trabajo del modelo (128×128×12) y no está alineado voxel a voxel con la
      serie NIfTI nativa.
- [x] Cuando `gradcam_available === false` pero hay un `gradcam_error`, se muestra ese motivo
      de forma honesta (no se oculta el fallo ni se simula un mapa).
- [x] Cuando el `AIAnalysis` tiene `biomarker_consistency` no nulo, aparece una tabla con una
      fila por feature (`feature`, `derived_value`, `expected_value_for_predicted_class`,
      `scaled_deviation`, `consistent`) y los valores de `distance_to_each_class` como chips,
      con la clase predicha resaltada, junto con el texto de referencia ya fijado en EPIC-12
      ("señal de consistencia indirecta... no es una atribución exacta del modelo").
- [x] Cuando `biomarker_consistency` es `null` pero hay `biomarker_consistency_error`, se
      muestra ese motivo de forma honesta.
- [x] Ninguno de estos paneles compite visualmente con el `NiftiViewer` como foco de la
      pantalla — siguen el sistema de tokens de EPIC-13 (`quietSurface()`, nunca un segundo
      `heroSurface()` en la misma pantalla).

## Alcance
Frontend únicamente: `frontend/src/pages/ImagingViewerPage.tsx`, componentes nuevos
`frontend/src/components/GradcamPanel.tsx` y
`frontend/src/components/BiomarkerConsistencyPanel.tsx`, utilidad nueva
`frontend/src/lib/npy.ts`, y las funciones/tipos nuevos en `frontend/src/api/analysis.ts`.

## Fuera de alcance
- Cualquier cambio de backend — los endpoints y campos que esta Epic consume
  (`GET /analyses/{id}/gradcam`, `gradcam_available`, `gradcam_error`,
  `biomarker_consistency`, `biomarker_consistency_error`) ya existen tal cual desde EPIC-3 y
  EPIC-12.
- Reproyectar/alinear el mapa de Grad-CAM al espacio nativo de la serie NIfTI — implicaría
  inventar un resampleo/affine no verificado, contrario a la ética de "no inventarnos nada"
  del proyecto (mismo motivo que EPIC-3 ya documentó para no forzarlo a NIfTI en el backend).
- LIME/Shapley — eso es EPIC-15.
- Panel de drift — eso es EPIC-16.

## Verificación
- `npm run lint`/`build`/`vitest run` (40/40): re-ejecutados de forma independiente, en verde.
- Lectura directa de `GradcamPanel.tsx`: la fórmula de indexado del array (`i*dimY*depth +
  j*depth + slice`) coincide exactamente con el C-order que usa el backend al serializar
  (`np.ascontiguousarray(...).tobytes()`), confirmado correcto.
- Verificación visual real con datos genuinos (no solo el mock de Miranda): las imágenes
  `unet_gradcam_patient101_{LV,RV,MYO}.png` reales (generadas por EDI en EPIC-1) muestran un
  heatmap limpio y localizado sobre cada estructura, confirmando que el patrón "informe" que
  vio el usuario en la captura inicial era del `.npy` sintético de prueba de Miranda, no un
  defecto del render — anotado explícitamente para no dejar la duda sin resolver.
- `security-review` (skill del orquestador, combinado con EPIC-15/16): sin hallazgos — EPIC-14
  no añade endpoints backend nuevos, solo consume datos ya expuestos y revisados en EPIC-3/
  EPIC-12.

### Ajuste post-cierre (feedback directo del usuario sobre las capturas)
El usuario, viendo capturas reales del panel, señaló dos problemas legítimos: (1) el heatmap
no tenía leyenda de colores, se leía como "una pelota difuminada sobre fondo verde" sin
contexto; (2) pidió explícitamente no usar datos sintéticos para verificar, sino procesar
datos reales. Ambos resueltos en el mismo cierre, sin reabrir la Epic como una nueva:
- Añadida `AttributionLegend` (barra baja→alta con etiquetas) bajo el slider.
- Añadido un segundo colormap "Standard" (jet, el mismo que ya usa
  `ml/scripts/run_explainability_showcase.py`) además del original "Website colors"
  (rampa cian on-brand), con un `ToggleButtonGroup` para alternar entre ambos —
  petición explícita del usuario.
- Verificación real, no sintética: se ejecutó `ml/cardiac_ai_ml/dl/run_inference_job.py`
  de verdad, con GPU real (`.venv-dl`, `torch.cuda.is_available()==True`), contra el
  checkpoint real de CNN3D y el paciente ACDC `patient101` real — el mismo caso ya usado en
  el showcase de EPIC-1. La predicción coincidió (`DILATED_CARDIOMYOPATHY`) y el array de
  atribución real (128×128×12, sin error) se guardó como `.npy` genuino (mismo mecanismo
  `np.save()` que usa `analysis_service.py` en producción) y se usó para capturar el panel
  en ambos modos — confirmado visualmente que ambas vistas muestran la misma estructura
  irregular real (no un blob sintético perfecto), solo con paletas distintas.

## Estado
Completada

## Contrato técnico (Shepard)

### 1. Grad-CAM — de `.npy` a algo pintable, sin tocar el backend

`GET /analyses/{analysis_id}/gradcam` ya devuelve bytes crudos de `np.save` sobre un array
`float32` `(128, 128, 12)` (`application/octet-stream`, ver EPIC-3 punto 2). El formato
`.npy` incluye su propio header (`\x93NUMPY`, versión, y un diccionario ASCII con `descr`,
`fortran_order`, `shape`) antes de los bytes crudos — **no hace falta un endpoint nuevo ni
metadata aparte**: el frontend puede parsear ese header él mismo.

Decisión: **no** se usa Niivue para este array. Niivue carga volúmenes por URL asumiendo
NIfTI (con su propio affine/spacing); forzar este array a ese formato exigiría fabricar un
affine que no es el real (ya descartado en el backend, ver EPIC-3 punto 2, exactamente por
la ética de "no inventarnos nada" del proyecto), y aunque se hiciera, el array vive en el
espacio de trabajo del modelo (128×128×12), con una forma distinta a la serie nativa — un
overlay Niivue superpuesto directamente sobre el volumen cargado implicaría una
correspondencia espacial exacta que no existe. En vez de fingir esa precisión, el mapa se
renderiza como su **propio panel independiente** de slices con mapa de calor (mismo patrón
visual que ya usa `ml/scripts/run_explainability_showcase.py` para el showcase offline —
imagen + heatmap superpuesto por slice — pero aquí sobre canvas en el navegador, no PNG
precompuesto), con su propio slider de slice (0 a 11) y una nota explícita de que no es un
overlay espacialmente exacto sobre la imagen NIfTI mostrada arriba.

**Nueva utilidad** `frontend/src/lib/npy.ts`:
```ts
export function parseNpyFloat32(buffer: ArrayBuffer): { shape: number[]; data: Float32Array }
```
Parsea el header `.npy` v1.0 (magic de 6 bytes + 2 bytes de versión + 2 bytes little-endian
de longitud de header + el dict ASCII, p. ej. `"{'descr': '<f4', 'fortran_order': False,
'shape': (128, 128, 12), }"`), valida `descr == "<f4"` (falla explícitamente, sin intentar
adivinar, si algún día cambia — nunca se decodifica a ciegas asumiendo el formato de hoy), y
devuelve `data` como una vista `Float32Array` sobre el resto del buffer. Solo soporta v1.0
(lo que `np.save` escribe por defecto para un array de este tamaño); si el magic/versión no
coincide, lanza con un mensaje claro en vez de silenciarlo.

**Nuevo componente** `frontend/src/components/GradcamPanel.tsx`: recibe el `Blob` ya
descargado (vía nueva función `fetchGradcamAttribution(analysisId, token): Promise<Blob>` en
`frontend/src/api/analysis.ts`, mismo patrón que `fetchSegmentationFile` en `api/imaging.ts`),
lo pasa por `arrayBuffer()` → `parseNpyFloat32`, y pinta cada slice `z` en un `<canvas>`
aplicando un colormap "jet" simple (interpolación de color por cuantiles del valor
normalizado — no hace falta una librería nueva, es una función pura de `value ∈ [0,1] →
rgb`). Vive como tarjeta `quietSurface()` separada, debajo del `NiftiViewer`, no dentro de
él — mantiene "un único hero por pantalla" (EPIC-13).

### 2. Biomarker consistency — tabla, mismo patrón que `ClassificationTab`

`biomarker_consistency`/`biomarker_consistency_error` ya viajan en `AIAnalysisOut` (backend)
pero **no están todavía en el tipo `AIAnalysis` del frontend** (`frontend/src/api/analysis.ts`
hoy solo tiene hasta `feature_attributions`) — añadir los cuatro campos nuevos
(`gradcam_available: boolean`, `gradcam_error: string | null`,
`biomarker_consistency: BiomarkerConsistency | null`,
`biomarker_consistency_error: string | null`) al tipo, con `BiomarkerConsistency` tipado
según el JSON exacto ya fijado en EPIC-12 (`predicted_class`, `reference_source`,
`per_feature: Array<{feature, derived_value, expected_value_for_predicted_class,
scaled_deviation, consistent}>`, `distance_to_each_class: Record<string, number>`).

**Nuevo componente** `frontend/src/components/BiomarkerConsistencyPanel.tsx`: tabla con
`TableContainer`/`Table` (mismo patrón MUI que `ClassificationTab.SimpleClassificationView`),
una fila por `per_feature[i]`, columna `consistent` como `Chip` (verde si `true`, ámbar si
`false` — no rojo: una desviación no implica error del modelo, es solo una señal), y los
`distance_to_each_class` como fila de `Chip`s con la clase predicha resaltada
(`color="primary"`, igual convención que ya usa el bloque de `probabilities` existente en
`ImagingViewerPage.tsx`). Se monta dentro del mismo `Card` de "AI analysis" ya existente,
debajo del bloque de `feature_attributions`, no en una tarjeta aparte — es la misma unidad de
información (el análisis de IA), solo una sección más.

### 3. División de trabajo
Toda la Epic es de **Miranda** (frontend). No requiere a Tali, EDI ni Garrus — ningún dato ni
endpoint nuevo, ningún cambio de infraestructura.

### 4. Seguridad
No aplica `security-review`: no hay endpoint nuevo, ni dato sensible nuevo expuesto — solo
renderizado de datos que ya viajan autenticados por endpoints RBAC ya auditados en EPIC-3 y
EPIC-12. Único cuidado de higiene normal: el colormap/parsing corre sobre datos numéricos
puros (no HTML/strings de usuario), no hay superficie de XSS nueva.
