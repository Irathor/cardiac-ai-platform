# LLM textual feedback (host-side Ollama bridge)

[EPIC-18: Feedback textual generado por LLM local (Qwen2.5) sobre el análisis de IA](epics/EPIC-18-feedback-textual-llm-local-qwen.md)
lets the doctor request a natural-language explanation of an already-completed `AIAnalysis`
(predicted class, probabilities, biomarker consistency) — presented explicitly as a suggestion,
never a diagnosis (see [ADR-9](adr/ADR-9-llm-local-ollama-qwen-feedback-textual.md) for why this
runs on a local LLM instead of the team's cloud-by-default stack).

Same host-bridge pattern as [`docs/dl-training-runner.md`](dl-training-runner.md) (ADR-8):
Ollama runs natively on the host (not in a Docker container — GPU passthrough into containers is
unreliable on this Windows + Docker Desktop setup), and the backend container reaches it via
`host.docker.internal`, which Docker Desktop on Windows resolves automatically with no extra
network configuration.

```
backend container --POST /api/generate--> Ollama (host, port 11434) --> qwen2.5:7b-instruct
```

## Starting it

Prerequisite: [Ollama](https://ollama.com) installed on the host.

```
ollama serve
ollama pull qwen2.5:7b-instruct
```

Leave `ollama serve` running in a terminal on the host before requesting a textual explanation
from the imaging viewer. The backend talks to it at `http://host.docker.internal:11434` by
default (configurable, see `app.core.config.Settings`).

This is a manual prerequisite, not something the backend can start by itself. If Ollama isn't
running, isn't reachable, or the model hasn't been pulled, the request fails cleanly with a
clear error — it never falls back to a fabricated or cached-looking text.

## API used

`POST /api/generate` — body `{"model": "qwen2.5:7b-instruct", "prompt": "<prompt>", "stream": false}`.
Returns `{"response": "<generated text>", "done": true, ...}` (200) once generation completes.

## What goes into the prompt

Only values the system has already computed for that `AIAnalysis`: `predicted_class`,
`probabilities`, `biomarker_consistency.per_feature`, and `distance_to_each_class`. The raw
Grad-CAM attribution array is never part of the prompt — it lives in the model's own working
space (128x128x12) and is not spatially aligned with the real anatomy (same reason it isn't
overlaid directly on the NIfTI viewer, see EPIC-3/EPIC-14), so asking the LLM to describe it
would mean fabricating a spatial interpretation with no verified basis.

## Caching

The generated text is stored on the `AIAnalysis` record itself and is not regenerated on every
page visit — there is an explicit action to force regeneration.

## Shared GPU with the DL training runner

Ollama and `training_runner_service.py` (ADR-8) both use the host's GPU. Running a retrain and
requesting a textual explanation at the same time may be slower for either — acceptable for this
single-operator development prototype.
