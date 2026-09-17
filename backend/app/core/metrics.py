"""Prometheus metrics for the DL inference actually served by this backend
(see docs/epics/EPIC-6-monitoring-basico.md and docs/adr/ADR-5-stack-monitoring-prometheus-grafana.md).

Two metrics only — `dl_inference_requests_total`'s `outcome` label covers
both "volume" (sum by `model_type`) and "success/failure rate" (sum by
`outcome`), so a separate volume-only counter would be redundant.

`observe_inference` is the single instrumentation point: it wraps exactly
the HTTP call to the host DL training runner inside
`app.services.dl_inference_client` (the `_post(...)` line in
`classify_cnn3d`/`segment_unet`), not the local staging/cleanup of files on
the shared `./data` mount around it. No other module imports
`prometheus_client` directly — `app.services.analysis_service` and
`app.services.auto_segmentation_service` keep calling `dl_inference_client`
exactly as before, unaware metrics exist at all.

Multiprocess mode (found post-instrumentation, real stack e2e check —
see docs/epics/EPIC-6-monitoring-basico.md): CNN3D inference
(`analysis_service.execute_analysis`) runs inside the Celery `worker`
container, a separate OS process from the `backend`/uvicorn process that
serves `GET /metrics`. `prometheus_client`'s default registry is in-memory
and per-process, so without multiprocess mode the worker's counters would
never be visible on `/metrics` — only the auto-segmentation path (which
runs synchronously inside the `backend` process) would ever show up.
`docker-compose.yml` sets `PROMETHEUS_MULTIPROC_DIR` (same value, same
shared volume) on both the `backend` and `worker` services; when that env
var is present, `prometheus_client` backs every `Counter`/`Histogram`
value with an mmapped file per process in that directory instead of a
plain in-memory float (this is the library's own built-in behaviour, see
https://prometheus.github.io/client_python/multiprocess/ — no extra
wiring needed here beyond setting the env var and creating the metrics
after it is set). `app.api.metrics` then reads all of those files back at
scrape time via `multiprocess.MultiProcessCollector`.
"""
import glob
import os
from collections.abc import Iterator
from contextlib import contextmanager
from time import monotonic

from prometheus_client import Counter, Histogram

_MULTIPROC_DIR = os.environ.get("PROMETHEUS_MULTIPROC_DIR")


def _cleanup_stale_files_for_this_pid() -> None:
    """`prometheus_client` multiprocess mode names each per-process mmap
    file `<metric_type>_<pid>.db` (e.g. `histogram_47.db`). If this OS pid
    was previously used by a process that died without cleanup (containers
    reuse low pids — pid 1, 7, ...) a stale file with today's pid can
    already exist in the shared directory, and this fresh process would
    start appending to (and being merged from) that old process's leftover
    values instead of starting at zero.

    Only deletes files matching *this* process's own pid — `backend` and
    `worker` share the same directory, and a currently-running sibling
    process's files (a different pid) are never touched. This runs once,
    at import time, before any `Counter`/`Histogram` in this module is
    created — see the official multiprocess docs' recommended pattern for
    services that don't use gunicorn's `child_exit` hook (which isn't
    available here — uvicorn/Celery, not gunicorn).
    """
    if not _MULTIPROC_DIR:
        return
    pid = os.getpid()
    for stale_file in glob.glob(os.path.join(_MULTIPROC_DIR, f"*_{pid}.db")):
        os.remove(stale_file)


_cleanup_stale_files_for_this_pid()

DL_INFERENCE_DURATION_SECONDS = Histogram(
    "dl_inference_duration_seconds",
    "Duration of the HTTP call to the host DL training runner for a single "
    "real-time inference request (classification or auto-segmentation). "
    "Excludes local staging/cleanup of the input file on the shared data mount.",
    labelnames=("model_type",),
    buckets=(0.5, 1, 2, 5, 10, 20, 30, 60, 90, 120),
)

DL_INFERENCE_REQUESTS_TOTAL = Counter(
    "dl_inference_requests_total",
    "Count of real-time inference requests served to the host DL training "
    "runner, by model type and outcome.",
    labelnames=("model_type", "outcome"),
)


@contextmanager
def observe_inference(model_type: str) -> Iterator[None]:
    """Times the wrapped block and records it in `dl_inference_duration_seconds`,
    then increments `dl_inference_requests_total` with `outcome="failure"` if
    `app.services.dl_inference_client.InferenceRunnerError` was raised inside
    the block (re-raised unchanged — this context manager never swallows it),
    or `outcome="success"` otherwise.

    Imports `InferenceRunnerError` lazily to avoid a circular import
    (`dl_inference_client` is the only caller of this context manager, and
    itself defines `InferenceRunnerError`).
    """
    from app.services.dl_inference_client import InferenceRunnerError

    start = monotonic()
    outcome = "success"
    try:
        yield
    except InferenceRunnerError:
        outcome = "failure"
        raise
    finally:
        DL_INFERENCE_DURATION_SECONDS.labels(model_type=model_type).observe(monotonic() - start)
        DL_INFERENCE_REQUESTS_TOTAL.labels(model_type=model_type, outcome=outcome).inc()
