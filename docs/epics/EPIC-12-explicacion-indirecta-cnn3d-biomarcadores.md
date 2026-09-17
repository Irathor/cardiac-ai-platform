# EPIC-12: Señal de consistencia indirecta para CNN3D vía biomarcadores auto-segmentados

## Historia de usuario
Como médico/usuario del portal clínico, quiero que un análisis CNN3D real muestre también
si los biomarcadores clínicos reales del caso (derivados por auto-segmentación U-Net) son
consistentes con la clase que predijo CNN3D, para tener una señal complementaria de
confianza además del mapa Grad-CAM, en el mismo lenguaje clínico (EF, volúmenes, masa) que
ya uso para el resto de análisis.

## Tipo
Normal

**Justificación**: no se entrena ni generaliza nada nuevo. Se reutiliza el U-Net ya servido
(EPIC-2) para obtener biomarcadores reales, y los prototipos/centroides por clase y la
distancia escalada que ya calcula `ml/cardiac_ai_ml/classification.py` para el clasificador
nearest-centroid (`FEATURE_NAMES`, `FEATURE_SCALES`, la misma lógica de distancia que usa
`_class_score`). Es una regla de negocio determinista sobre modelos/datos que ya existen, no
una capacidad de IA/ML nueva — por eso no es "Con IA" pese a que ambos modelos que reutiliza
(U-Net, nearest-centroid) sí lo son.

## Bloqueada por
EPIC-2 (Servir los modelos reales (U-Net/CNN3D) desde la API de inferencia) y EPIC-3
(Explicabilidad con Grad-CAM integrada en el flujo de análisis servido) — ambas completadas.
Esta Epic necesita el U-Net real servido (EPIC-2) y el patrón ya asentado de "explicación
complementaria que no puede tumbar el `AIAnalysis` principal si falla" (EPIC-3, punto 4) para
tener sentido y para no reinventar ese manejo de fallo.

## Criterios de aceptación
- [x] Cuando `execute_analysis` sigue el camino CNN3D_CLASSIFICATION (rama
      `production_cnn3d is not None` en `analysis_service.py`), además del Grad-CAM ya
      servido (EPIC-3) se ejecuta también la auto-segmentación U-Net sobre los mismos
      `ed_series`/`es_series` del caso, reutilizando `auto_segmentation_service
      .generate_auto_segmentation` (que a su vez reutiliza `dl_inference_client.segment_unet`
      de EPIC-2) — no se reimplementa la llamada al runner ni el cómputo de biomarcadores.
      Se generan dos `Segmentation` reales (una por fase), igual que si un usuario hubiera
      pedido auto-segmentación manualmente sobre esas series.
- [x] Tras generar ambas segmentaciones, el vector de biomarcadores del caso
      (`EJECTION_FRACTION`, `LV_EDV`, `RV_EDV`, `LV_MASS`) se obtiene reutilizando
      `analysis_service.collect_features(db, study)` tal cual — la misma función que ya usa
      el camino nearest-centroid — en vez de reimplementar la combinación ED/ES.
- [x] Ese vector se compara contra los prototipos por clase que ya usa el camino
      nearest-centroid (`production_model.prototypes` si hay un modelo nearest-centroid
      PRODUCTION, o los prototipos demo si no lo hay — misma selección que ya hace
      `execute_analysis` en su rama `else`), reutilizando la lógica de distancia
      escalada existente en `ml/cardiac_ai_ml/classification.py` (mismo `FEATURE_SCALES`
      y misma fórmula que `_class_score`) — no se inventan umbrales ni normalizaciones
      nuevas. EDI expone esta lógica como función pública nueva en `classification.py`
      (hoy `_class_score`/`_DEMO_PROTOTYPES` son privados al módulo; se promocionan o se
      envuelven en una función pública nueva, p. ej. `biomarker_consistency(features,
      prototypes, predicted_class)` — el nombre exacto y la forma del dataclass/dict de
      retorno los decide EDI, ver "Contrato técnico" abajo) devolviendo, como mínimo, por
      cada feature: el valor derivado, el valor esperado por la clase predicha, la
      desviación escalada y si cae dentro de un umbral de consistencia razonable
      (mismo orden de magnitud que `FEATURE_SCALES`, no un valor inventado sin relación
      con la escala ya usada en el resto del módulo).
- [x] El resultado se expone en `AIAnalysisOut` como un campo nuevo `biomarker_consistency`
      (JSON, nullable) con esta forma mínima:
      ```json
      {
        "predicted_class": "DILATED_CARDIOMYOPATHY",
        "reference_source": "<production_model.name>@<production_model.id>" o "demo-heuristic-v1",
        "per_feature": [
          {
            "feature": "EJECTION_FRACTION",
            "derived_value": 28.4,
            "expected_value_for_predicted_class": 25.0,
            "scaled_deviation": 0.23,
            "consistent": true
          }
        ],
        "distance_to_each_class": {"NORMAL": 3.1, "DILATED_CARDIOMYOPATHY": 0.3, "...": "..."}
      }
      ```
      `distance_to_each_class` (distancia escalada a cada prototipo, reutilizando la misma
      fórmula) da contexto barato de calcular (ya se itera sobre todos los prototipos) sin
      esfuerzo adicional real; no es una decisión grande, solo un campo más del mismo
      cálculo.
- [x] `biomarker_consistency` se documenta explícitamente (docstring en el modelo y/o
      comentario junto a `CNN3D_NO_FEATURE_ATTRIBUTION_REASON`) como **señal de consistencia
      indirecta**, no como una atribución exacta tipo Shapley — nunca se confunde ni se
      mezcla con `feature_attributions`, que sigue siendo `null` para CNN3D por el motivo ya
      documentado en `CNN3D_NO_FEATURE_ATTRIBUTION_REASON`. El texto de referencia sugerido:
      "Señal de consistencia indirecta entre los biomarcadores derivados por auto-
      segmentación U-Net y los prototipos de la clase predicha por CNN3D — no es una
      atribución exacta del modelo, es una comparación posterior con un clasificador
      distinto (nearest-centroid)."
- [x] Manejo de fallo (mismo criterio que Grad-CAM en EPIC-3, punto 4): si la auto-
      segmentación U-Net falla — no hay modelo U-Net PRODUCTION
      (`ModelNotAvailableError`) o el runner falla (`InferenceRunnerError`, p. ej. sin
      runner GPU) — el `AIAnalysis` de CNN3D **no falla por eso**; queda COMPLETED con
      `biomarker_consistency=None` y un campo `biomarker_consistency_error` con el motivo
      honesto. El error se captura en un `try/except` propio alrededor de este bloque
      dentro de `execute_analysis`, sin relanzar — un fallo aquí nunca debe convertirse en
      el `except (MissingPhaseDataError, InferenceRunnerError)` que marca todo el análisis
      como FAILED.
- [x] Tests reales (no solo mocks de la lógica de distancia): al menos un test de
      integración en `ml` que ejercite `biomarker_consistency`/función equivalente con
      prototipos reales y biomarcadores reales/sintéticos, comprobando valores concretos; al
      menos un test en `backend` con U-Net real disponible (o mockeado de forma explícita y
      señalada como tal) que verifique el camino feliz completo (`AIAnalysis` con
      `biomarker_consistency` poblado) y el camino de fallo (U-Net no disponible ⇒
      `AIAnalysis` sigue COMPLETED con `biomarker_consistency_error` y sin tumbar la
      clasificación).

## Alcance
Backend (`analysis_service.py`, migración Alembic, `AIAnalysisOut`) e integración con
`ml/cardiac_ai_ml/classification.py` (EDI) para exponer la función pública de consistencia.
Reutiliza `auto_segmentation_service.py` (EPIC-2) y `dl_inference_client.segment_unet` sin
modificarlos.

## Fuera de alcance
- Cambiar el comportamiento del clasificador nearest-centroid (`classify_with_prototypes`,
  `explain_with_prototypes`) — se reutiliza tal cual, no se toca.
- Cambiar Grad-CAM (EPIC-3) — ambas explicaciones (Grad-CAM y esta señal de consistencia)
  conviven como piezas independientes del mismo `AIAnalysis`, cada una con su propio campo
  de error.
- Entrenar o ajustar nada nuevo (ni U-Net ni los prototipos/centroides).
- Renderizado visual de `biomarker_consistency` en el frontend — igual que Grad-CAM en
  EPIC-3, el criterio de aceptación queda satisfecho por exponer el dato completo en
  `AIAnalysisOut`; el render (tabla/gráfico comparativo en la pantalla de informe) queda
  como fast-follow explícito en `docs/BACKLOG.md` si no entra en el mismo lote.

## Contrato técnico (Shepard)

Revisé la propuesta de Liara contra `analysis_service.py`, `auto_segmentation_service.py` y
`classification.py` reales. La base es correcta (invocación directa en proceso, mismo
patrón no-bloqueante que Grad-CAM) pero tenía dos huecos que cierro aquí: cómo se obtiene el
`actor: User` que `generate_auto_segmentation` exige, y la fórmula exacta de distancia (no
basta con decir "la misma que `_class_score`" — hay que fijar si se expone la distancia al
cuadrado o la euclídea, porque cambia cómo se lee `distance_to_each_class`).

### 1. Dónde se calcula
Confirmado: nueva función pública en `ml/cardiac_ai_ml/classification.py`, invocación
directa en el mismo proceso del backend (no subproceso — a diferencia de Grad-CAM, que vive
en `run_inference_job.py`), igual que ya se hace hoy con `classify_with_prototypes`/
`explain_with_prototypes`.

**Firma**: `biomarker_consistency(features: dict[str, float], prototypes: Prototypes,
predicted_class: str) -> BiomarkerConsistency` (dataclass, mismo estilo que
`ClassificationResult`/`FrameBiomarkers`, no un dict suelto). `BiomarkerConsistency` expone
un método `as_dict()` que produce exactamente el JSON serializable de la sección "Formato"
de abajo — así Tali no reimplementa el shape a mano en el backend, igual que
`FrameBiomarkers.as_measurements()` ya hace para `auto_segmentation_service`.

**Normalización**: sí, reutiliza `FEATURE_NAMES`/`FEATURE_SCALES` — sin escalar, comparar
EF (0-100) contra LV_MASS (gramos) directamente no tendría sentido, es la misma razón por
la que `_class_score` ya escala. Fijo la fórmula exacta (Liara la dejó ambigua):
- `scaled_deviation` por feature = `(derived_value - expected_value) / FEATURE_SCALES[name]`
  (con signo, no valor absoluto — permite ver en qué dirección se desvía, más útil
  clínicamente que solo la magnitud).
- `consistent` por feature = `abs(scaled_deviation) <= 1.0` (dentro de un "spread típico" de
  la clase predicha — mismo orden de magnitud que `FEATURE_SCALES`, no un umbral inventado).
- `distance_to_each_class` = distancia **euclídea** en unidades escaladas, es decir
  `sqrt(-_class_score(prototype, features))` para cada clase — no la distancia al cuadrado
  cruda que devuelve `_class_score` internamente. Motivo: una distancia euclídea crece
  linealmente y es comparable feature a feature con `scaled_deviation`; el valor al cuadrado
  distorsiona esa lectura para quien consuma el JSON. `_class_score` se reutiliza tal cual
  como pieza interna (se queda privada), no hace falta promocionarla.

### 2. Dónde se orquesta (Tali, `analysis_service.execute_analysis`)
Dentro de la rama `production_cnn3d is not None`, después de fijar
`analysis.predicted_class` y del bloque de Grad-CAM, en un `try/except` propio que **no**
puede escalar al `except (MissingPhaseDataError, InferenceRunnerError)` que marca todo el
análisis como FAILED (mismo patrón que el punto 4 de EPIC-3).

**Sobre qué series**: ambas, `ed_series` **y** `es_series` (ya resueltas arriba en la misma
rama vía `_ed_es_series`, no se vuelven a buscar). Confirmo la propuesta de Liara: EF, LV_EDV
y RV_EDV vienen de la fase ED, LV_MASS también de ED, pero `collect_features` (que se
reutiliza tal cual) necesita el volumen ES para calcular la fracción de eyección — sin
auto-segmentar ambas fases no hay biomarcadores completos. No hace falta correr U-Net sobre
más series que estas dos.

**Persistidas de verdad, no efímeras**: confirmo la propuesta de Liara. Crear dos
`Segmentation` reales vía `auto_segmentation_service.generate_auto_segmentation` (reutilizada
sin modificar) es la opción correcta frente a un cálculo efímero que descarte la máscara: (a)
evita reimplementar en paralelo una versión "solo para calcular, no guardar" de una función
que ya existe y ya hace exactamente lo que hace falta — divergencia de código sin beneficio
real; (b) dota de valor añadido gratis: el usuario puede luego abrir esas segmentaciones en
el visor igual que si las hubiera pedido a mano, coherente con cómo ya se trata una
auto-segmentación en el resto del sistema. El coste es ejecutar el runner U-Net dos veces
por cada análisis CNN3D — aceptable porque `execute_analysis` ya corre entero dentro de un
worker Celery asíncrono, no en el camino de una petición HTTP.

**Hueco que cierro (no estaba en la propuesta de Liara)**: `generate_auto_segmentation`
exige un `actor: User`, no un `user_id`. `execute_analysis` hoy solo tiene
`analysis.requested_by` (UUID). Tali debe resolverlo con `db.get(User,
analysis.requested_by)` antes de llamar a `generate_auto_segmentation` (dos veces, ED y ES);
si ese `User` ya no existe (caso raro, cuenta borrada), se trata como el mismo tipo de fallo
que "no hay modelo U-Net disponible": se captura, no se relanza, y
`biomarker_consistency_error` lo explica ("no se pudo identificar al usuario solicitante
para generar la auto-segmentación").

### 3. Qué prototipos usar
Confirmo la propuesta de Liara sin cambios: `production_model.prototypes` del modelo
nearest-centroid PRODUCTION (`MODEL_NAME`) si existe, si no los prototipos demo — exactamente
la misma selección que ya hace la rama `else` de `execute_analysis`. No es un problema de
coherencia semántica usar centroides de un modelo distinto al que predijo: el criterio de
aceptación y el texto de referencia ya dejan explícito que esto es "una comparación
posterior con un clasificador distinto (nearest-centroid)", no una explicación nativa de
CNN3D — igual que Grad-CAM no pretende ser Shapley. Mientras `reference_source` deje claro
qué prototipos se usaron (ver formato abajo), no hay ambigüedad para quien lea el resultado.

### 4. Formato y persistencia
Confirmo el JSON de la propuesta de Liara (`predicted_class`, `reference_source`,
`per_feature[]`, `distance_to_each_class`) sin cambios de forma, más el ajuste de fórmula del
punto 1. Si no hay biomarcadores completos o falla el U-Net, `biomarker_consistency = None`
(no un JSON con campos en `null` a medias).

**Migración Alembic (Tali)** — columnas propias en `ai_analyses`, **no** reutilizar la
columna `features` existente: `features` ya tiene un significado establecido y documentado
(`CNN3D_NO_FEATURE_ATTRIBUTION_REASON`) como "vector tabular que el modelo realmente
puntuó", que para CNN3D es intencionalmente `null`; mezclar ahí una estructura de
comparación distinta rompería ese contrato ya asentado, exactamente el mismo motivo por el
que Grad-CAM (EPIC-3) usó columnas nuevas en vez de reutilizar algo existente:
- `biomarker_consistency JSON NULL`
- `biomarker_consistency_error VARCHAR(2000) NULL`

Añadir los campos equivalentes a `app/models/ai_analysis.py` y a `AIAnalysisOut`.

### 5. Manejo de fallo
Confirmo el patrón no bloqueante de Liara, mismo criterio que Grad-CAM (EPIC-3, punto 4):
un `try/except` propio alrededor de todo el bloque (auto-segmentación ED, auto-segmentación
ES, `collect_features`, `biomarker_consistency`) capturando
`(ModelNotAvailableError, InferenceRunnerError, MissingPhaseDataError)` — las tres son
posibles aquí (no hay U-Net PRODUCTION, falla el runner, o `collect_features` no encuentra
lo que espera pese a la auto-segmentación recién creada). Si se captura cualquiera,
`analysis.biomarker_consistency = None` y `analysis.biomarker_consistency_error =
f"Consistencia de biomarcadores no disponible para este análisis: {exc}"`; el `AIAnalysis`
sigue su curso normal hacia COMPLETED. Nunca se relanza hacia el `except` que marca FAILED.

### 6. División de trabajo EDI/Tali (paralelizable desde ya)
- **EDI**: `biomarker_consistency()` + `BiomarkerConsistency` (dataclass +`as_dict()`) en
  `ml/cardiac_ai_ml/classification.py`, con el test de integración con prototipos y
  biomarcadores reales/sintéticos que pide el criterio de aceptación. No depende de nada de
  `backend/` — puede empezar ya con la firma y fórmula fijadas arriba.
- **Tali**: orquestación en `analysis_service.execute_analysis` (resolución del `User`
  actor, doble auto-segmentación, `collect_features`, llamada a la función de EDI),
  migración Alembic, campos en `AIAnalysis`/`AIAnalysisOut`, tests backend (camino feliz +
  camino de fallo). Puede avanzar en paralelo contra este contrato usando un stub de
  `biomarker_consistency` que devuelva la forma acordada; sustituye el stub por la función
  real de EDI antes del cierre de la Epic — mismo patrón ya usado en EPIC-2/3/4/11.

## Verificación
Pendiente — se completa al cierre de la Epic siguiendo el checkpoint único del equipo
(verificación cara una sola vez, al final, con el stack relevante).

## Verificación
- `ml`: 35/35 tests en verde (incluye 5 nuevos de `biomarker_consistency`, valores calculados
  a mano contra un prototipo de referencia — caso consistente y caso inconsistente), `ruff
  check` limpio.
- `backend`: 138/138 tests en verde (incluye los 2 nuevos: camino feliz con Segmentations
  reales creadas vía auto-segmentación de ED/ES, y camino de fallo no bloqueante), `ruff
  check` limpio. Migración `0010` head único.
- Contrato EDI↔Tali verificado: firma exacta de `biomarker_consistency()`/
  `BiomarkerConsistency.as_dict()` consumida tal cual por `analysis_service.py`, sin
  discrepancias (Tali no necesitó stub, EDI ya había terminado).
- `security-review` (skill del orquestador, combinado con EPIC-7): sin hallazgos —
  `analysis.requested_by` confirmado como campo de confianza poblado server-side, sin ruta
  para que un llamante inyecte un actor o dispare auto-segmentación sobre series ajenas;
  `biomarker_consistency` persistido es puramente numérico, sin IDs ni rutas de archivo.

## Estado
Completada
