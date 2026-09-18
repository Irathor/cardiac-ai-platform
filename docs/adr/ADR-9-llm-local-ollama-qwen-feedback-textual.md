# ADR-9: LLM local vía Ollama (Qwen2.5) para el feedback textual — desviación de "nube por defecto"

## Estado
Aceptada

## Contexto
[EPIC-18: Feedback textual generado por LLM local (Qwen2.5) sobre el análisis de IA —
sugerencia interpretable para el profesional](../epics/EPIC-18-feedback-textual-llm-local-qwen.md)
necesita un LLM que redacte, en lenguaje natural, una explicación del análisis de IA ya
calculado (clase predicha, probabilidades, consistencia de biomarcadores) para presentarla al
médico como sugerencia de apoyo.

Las convenciones del equipo (`~/.claude/CLAUDE.md`, stack de IA por defecto) establecen "nube
por defecto, local solo si hay datos sensibles" para el proveedor de LLM. Aquí la razón de ir
local **no** es sensibilidad de los datos: este es un prototipo de investigación que trabaja
sobre el dataset público/sintético ACDC, sin datos de pacientes reales. La razón es que el
usuario pidió explícitamente un modelo gratuito ("como Qwen"); al preguntarle nube vs. local
(decisión grande de proveedor, ver "Regla de autonomía"), confirmó que prefiere local.

Se verificó contra el repositorio real de modelos de Ollama (no de memoria) que `qwen2.5:7b-instruct`
existe (~4.7GB, contexto 32K) y que la API real es `POST /api/generate` con body
`{model, prompt, stream: false}`, devolviendo `{response: "...", done: true, ...}` sobre
`http://localhost:11434` (puerto por defecto de Ollama).

Opciones valoradas:
1. **LLM en la nube** (stack por defecto del equipo) — descartado por decisión explícita del
   usuario: quiere un modelo gratuito y sin dependencia de una API de pago externa.
2. **Ollama dentro de un contenedor Docker nuevo** — descartado por el mismo motivo ya
   documentado en [ADR-8](ADR-8-servicio-puente-host-entrenamiento-gpu.md) para U-Net/CNN3D: el
   GPU passthrough a contenedores en esta máquina (Windows + Docker Desktop) resultó frágil en
   pruebas previas de este proyecto. Además introduciría un contenedor persistente nuevo (coste
   de RAM/GPU permanente) solo para servir el modelo.
3. **Ollama corriendo nativo en el host**, alcanzado por el backend (en Docker) vía
   `http://host.docker.internal:11434` — mismo patrón exacto que ya usa
   `ml/scripts/training_runner_service.py` (ADR-8) para que los contenedores lleguen a procesos
   del host en Windows sin configuración de red adicional. Elegida.

## Decisión
El backend (Tali) llama a Ollama corriendo nativo en el host vía
`http://host.docker.internal:11434/api/generate`, con `model: "qwen2.5:7b-instruct"` y
`stream: false`. Ollama **no** se despliega como contenedor Docker — es un prerequisito manual
del host, igual que el servicio puente de entrenamiento DL de ADR-8.

Prerequisito manual: `ollama serve` + `ollama pull qwen2.5:7b-instruct` corriendo en el host
antes de usar la feature. Documentado en `docs/llm-explanation.md` (nuevo, análogo a
`docs/dl-training-runner.md`). Si Ollama no está corriendo o falla, la generación del texto
falla de forma honesta (error claro), nunca con un texto inventado o un fallback silencioso a
otro proveedor.

## Consecuencias
- **Ventaja**: sin coste de API ni dependencia de red externa; reutiliza exactamente el mismo
  patrón de acceso host↔contenedor ya validado y documentado en ADR-8, sin introducir un
  mecanismo nuevo que el equipo tenga que aprender o mantener aparte.
- **Desventaja/deuda asumida**: descarga inicial de ~4.7GB la primera vez (`ollama pull`);
  comparte GPU del host con el runner de entrenamiento DL (`training_runner_service.py`) — si
  ambos corren a la vez, la generación de texto o el entrenamiento pueden ir más lentos.
  Aceptable para este prototipo de un solo operador; no es una feature de baja latencia crítica.
- **Superficie de seguridad**: mismo criterio ya aceptado en ADR-8 — Ollama expone su API sin
  autenticación propia, pero solo alcanzable vía `host.docker.internal` desde los contenedores
  de esta máquina de desarrollo, no expuesta a red externa. Si el proyecto se despliega en un
  host compartido o multi-operador, esto debería revisarse igual que se señaló en ADR-8.
- **Impacto en otros módulos**: ninguno sobre el flujo de análisis existente (Grad-CAM,
  biomarker consistency) — el texto del LLM es un enriquecimiento aditivo sobre un `AIAnalysis`
  ya completado, nunca sustituye ni modifica los campos ya calculados. `app/core/config.py`
  añade una URL de Ollama configurable; no se toca `docker-compose.yml` porque Ollama no es un
  servicio del compose, igual que el runner de entrenamiento.
