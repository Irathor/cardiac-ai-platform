# DL training runner (host-side bridge for U-Net / CNN3D)

The nearest-centroid classifier trains entirely inside the Celery `worker` container
(`app.services.training_service.execute_training`). The two deep-learning models — 2D U-Net
segmentation and CNN3D diagnosis classification — do not: they need a real GPU, and GPU
passthrough into the `worker` container isn't available on this deployment. Instead they keep
running exactly the way they already did before this feature (`.venv-dl`, on the host), just
triggered by the worker over HTTP instead of by hand.

```
worker container --POST /jobs--> training_runner_service.py (host, .venv-dl) --subprocess--> train_segmentation.py / train_classification.py (GPU)
                  <--poll GET /jobs/{id}--
```

Both sides read/write the same `./data` directory — bind-mounted into the containers at `/data`
(see `docker-compose.yml`) and used directly on the host — so the trained weights and metrics
JSON never need to be transferred over HTTP; the worker just reads them off the shared mount once
the runner reports `COMPLETED`.

## Starting it

Prerequisite: `.venv-dl` already set up per `ml/cardiac_ai_ml/dl/train_segmentation.py`'s own
docstring (a real PyTorch + CUDA environment, `pip install -e ".[dl]"`).

```
ml/.venv-dl/Scripts/python ml/scripts/training_runner_service.py
```

Optionally pass `--port` (default `8800` — must match `app.core.config.Settings.training_runner_url`,
`http://host.docker.internal:8800` by default). Leave it running in a terminal on the host before
triggering a U-Net or CNN3D retrain from the admin UI — Docker Desktop on Windows resolves
`host.docker.internal` from inside the containers with no extra configuration.

This is a manual prerequisite, not something Celery can start by itself. If it isn't running (or
crashes mid-job), the training run backing it fails cleanly with a clear error message — it is
never left stuck in `RUNNING` (see `execute_dl_training`'s ~90 minute poll timeout).

## API

- `POST /jobs` — body `{"model_type": "UNET_SEGMENTATION" | "CNN3D_CLASSIFICATION"}`. Returns
  `{"job_id": "<uuid>"}` immediately; the actual training subprocess is launched and polled in a
  background thread.
- `GET /jobs/{job_id}` — returns
  `{"status": "QUEUED"|"RUNNING"|"COMPLETED"|"FAILED", "log_tail": "<last ~4000 chars of stdout+stderr>", "result_path": "<path relative to data/, or null until COMPLETED>", "error": "<str or null>"}`.

In-memory only — one process, no persistence. A restart loses any in-flight job.
