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

### Real-time inference (EPIC-2)

Two more endpoints reuse this same host-side GPU bridge for a single forward pass instead of a
whole training run — `app.services.analysis_service` (real `AIAnalysis` classification, CNN3D) and
`app.services.auto_segmentation_service` (real `Segmentation` generation, U-Net) both call these via
`app.services.dl_inference_client`, exactly the same way `execute_dl_training` calls `POST /jobs`.
Unlike training, both block and return the result directly (one real GPU forward pass takes
milliseconds to a few seconds — no need for the QUEUED/RUNNING/polling machinery `/jobs` needs for a
60-epoch run) by launching `python -m cardiac_ai_ml.dl.run_inference_job` as a short subprocess.
Both endpoints require real CUDA in that subprocess — see
`cardiac_ai_ml.dl.inference._require_cuda_device` — and fail with a clear `502` (surfaced by
`_run_inference_subprocess` reading the job's `{"error": ...}` result) rather than ever silently
falling back to CPU.

Both endpoints take a path *relative to* this process's own `DATA_ROOT` (the host's view of the
same `./data` directory the containers bind-mount at `/data`) — the calling container stages the
relevant series' raw bytes onto that shared mount under `data/tmp/inference/` first (since this
process, running directly on the host rather than in a container, cannot reach MinIO/object storage
directly), and removes the staged file again once the call returns.

- `POST /inference/classify` — body `{"ed_relative_path": "tmp/inference/<uuid>.nii.gz", "es_relative_path": "tmp/inference/<uuid>.nii.gz"}`.
  Runs the real `data/models/cnn3d/cnn3d.pt` checkpoint. Returns
  `{"predicted_class": "<DiagnosisClass value>", "probabilities": {"<class>": <float>, ...}}` (200),
  `409` if no checkpoint exists yet, `400` for a bad/missing path, `502` if the inference subprocess
  itself fails.
- `POST /inference/segment` — body `{"image_relative_path": "tmp/inference/<uuid>.nii.gz"}`. Runs
  the real `data/models/unet2d.pt` checkpoint. Returns
  `{"mask_base64": "<base64 int16 mask bytes>", "mask_shape": [H, W, Z], "voxel_spacing_x_mm": <float>, "voxel_spacing_y_mm": <float>, "voxel_spacing_z_mm": <float>}`
  (200) — same status codes as `/inference/classify` for the failure cases.

Same manual prerequisite as training: if this process isn't running, both calls fail with a clear
`InferenceRunnerError` (surfaced as an HTTP 503 from the backend endpoint/a FAILED `AIAnalysis`),
never a hang or a fabricated result.
