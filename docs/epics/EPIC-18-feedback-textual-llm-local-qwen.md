# EPIC-18: Feedback textual generado por LLM local (Qwen2.5) sobre el análisis de IA — sugerencia interpretable para el profesional

## Historia de usuario
Como médico/usuario del portal clínico, quiero pedir desde el visor de imágenes un texto en
lenguaje natural que explique el análisis de IA ya calculado (clase predicha, probabilidades y
consistencia de biomarcadores), para entender más rápido qué detectó el sistema sin tener que
interpretar el JSON crudo — siempre como una sugerencia de apoyo, nunca como un diagnóstico.

## Tipo
Con IA (requiere de verdad un LLM que genere texto natural a partir de valores estructurados;
no es una plantilla de negocio determinista).

## Bloqueada por
Ninguna — consume [EPIC-3: Explicabilidad con Grad-CAM integrada en el flujo de análisis
servido](EPIC-3-gradcam-integrado-flujo-servido.md) y [EPIC-12: Señal de consistencia
indirecta para CNN3D vía biomarcadores auto-segmentados](EPIC-12-explicacion-indirecta-cnn3d-biomarcadores.md),
ambas ya completadas; esta Epic solo consume lo que ya exponen.

## Criterios de aceptación
- [x] Desde `ImagingViewerPage`, cuando el `AIAnalysis` activo es `COMPLETED`, el doctor puede
      pedir explícitamente (botón, no automático) un texto generado que explique el análisis en
      lenguaje natural.
- [x] El prompt enviado al LLM se construye únicamente a partir de valores numéricos/categóricos
      ya calculados por el sistema (`predicted_class`, `probabilities`,
      `biomarker_consistency.per_feature`, `distance_to_each_class`) — nunca a partir de los
      píxeles crudos del array de Grad-CAM, que no está alineado espacialmente con la anatomía
      real (mismo motivo ya documentado en EPIC-14 para no superponerlo al visor); generar una
      interpretación espacial a partir de ese array sería fabricar información no verificada.
- [x] El texto generado se muestra siempre junto a un aviso visible (no solo una etiqueta de UI
      discreta) indicando que es una sugerencia de apoyo a la decisión redactada por un LLM a
      partir de números ya calculados por el sistema, nunca un diagnóstico, y que el profesional
      es quien decide si tiene sentido clínico.
- [x] Si Ollama no está corriendo, no responde, o falla de cualquier forma, el sistema falla de
      forma honesta con un mensaje de error claro — nunca se muestra un texto inventado ni se
      simula una respuesta como fallback silencioso.
- [x] El texto generado se cachea en el propio `AIAnalysis` (no se regenera en cada visita a la
      pantalla); existe una acción explícita para forzar la regeneración.

## Alcance
- Backend (Tali): nuevo campo(s) persistidos en `AIAnalysis` para el texto cacheado, endpoint
  para solicitar generación/regeneración, cliente HTTP hacia Ollama (`POST /api/generate`,
  `http://host.docker.internal:11434`, modelo `qwen2.5:7b-instruct`, `stream: false`),
  construcción del prompt a partir de los campos ya calculados listados arriba, manejo de fallo
  honesto si Ollama no responde.
- Frontend (Miranda): control en `ImagingViewerPage` para solicitar/regenerar el texto, panel de
  presentación del resultado con el aviso de "sugerencia, no diagnóstico" siempre visible,
  manejo del estado de error explícito.
- Documentación (Liara): esta Epic, [ADR-9](../adr/ADR-9-llm-local-ollama-qwen-feedback-textual.md)
  y `docs/llm-explanation.md` (prerequisito manual de Ollama, análogo a
  `docs/dl-training-runner.md`).

## Fuera de alcance
- Cualquier intento de alinear o interpretar espacialmente el array de Grad-CAM dentro del
  prompt o del texto generado — ya descartado explícitamente en EPIC-3/EPIC-14 por la misma
  razón (no hay affine/resampleo verificado, y forzarlo sería fabricar información).
- Streaming de la respuesta del LLM token a token — el contrato usa `stream: false` de Ollama;
  si en el futuro se justifica una experiencia de streaming, es una Epic aparte.
- Cualquier LLM en la nube como alternativa/fallback si Ollama falla — el fallo es honesto, no
  hay conmutación automática a otro proveedor (eso reabriría la decisión grande ya resuelta en
  ADR-9 de ir local).
- Ajustar o reentrenar el propio modelo Qwen2.5 — se usa el modelo instruct tal cual se publica.
- Traducir o localizar el texto generado a idiomas distintos del que ya usa el resto del portal.

## Verificación
- Backend: migración `0011_ai_analysis_llm_explanation.py` (columnas `llm_explanation`/
  `llm_explanation_error`), `app/services/llm_explanation_service.py` (prompt construido solo a
  partir de `predicted_class`/`probabilities`/`biomarker_consistency`, cliente httpx hacia Ollama,
  `LlmExplanationError` nunca fabrica texto), `POST /analyses/{id}/explanation` (RBAC
  `ADMIN`/`DOCTOR`, misma comprobación `_load_analysis`/`_load_study_for_viewer` que ya usan
  `get_analysis`/`get_analysis_gradcam`, cacheo salvo `force=true`).
- `pytest` completo del backend: 152/152 en verde, incluidos 4 tests nuevos (generación real
  contra un Ollama simulado vía monkeypatch de `httpx.post`, cacheo, `force=true` regenera,
  fallo honesto con Ollama genuinamente inalcanzable — sin mock, error real de conexión — y RBAC
  de doctor no asignado). `ruff check` limpio.
- Frontend: `LlmExplanationPanel.tsx` (mismo patrón lazy-fetch-al-expandir que `GradcamPanel`),
  aviso de "sugerencia, no diagnóstico" siempre visible al expandir. `npm run lint`/`build`/
  `vitest run`: 43/43 en verde (3 tests nuevos del panel: genera y muestra el texto, muestra el
  error honesto sin fabricar nada, regenerar llama con `force=true`).
- `security-review` (skill del orquestador): sin hallazgos — RBAC verificado consistente con
  `gradcam`, `ollama_url` viene solo de configuración de servidor (no hay SSRF con datos de
  request), el prompt no incluye texto libre de usuario, el texto generado se renderiza como
  texto plano en React (sin `dangerouslySetInnerHTML`).
- Verificación en vivo end-to-end (Ollama real + `qwen2.5:7b-instruct` real) queda pendiente de
  que el usuario instale Ollama en su máquina — el prerequisito manual documentado en
  `docs/llm-explanation.md`; hasta entonces, el camino de fallo honesto (sin Ollama corriendo) sí
  se verificó en vivo, no solo con mocks (ver test de arriba sin monkeypatch).

## Estado
Completada

## Contrato técnico (Shepard)

### Cliente Ollama (Tali)
`POST http://host.docker.internal:11434/api/generate` con body
`{"model": "qwen2.5:7b-instruct", "prompt": "<prompt construido>", "stream": false}`, respuesta
`{"response": "<texto>", "done": true, ...}` — mismo patrón `host.docker.internal` que ya usa
`ml/scripts/training_runner_service.py` (ver ADR-8) para alcanzar procesos del host desde los
contenedores. Sin autenticación propia de Ollama (igual criterio de riesgo aceptado que ADR-8:
máquina de desarrollo/operador único, no expuesta a red externa).

### Prerequisito manual
`ollama serve` + `ollama pull qwen2.5:7b-instruct` corriendo en el host antes de usar la feature.
Documentado en `docs/llm-explanation.md`, nunca arrancado automáticamente por el backend ni por
`docker compose up` — si Ollama no responde, la generación falla con un mensaje claro en vez de
quedarse colgada o simular una respuesta.
