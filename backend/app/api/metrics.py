"""`GET /metrics` — Prometheus scrape endpoint, mounted at the app root (not
under `/api/v1`, see docs/epics/EPIC-6-monitoring-basico.md's "Contrato
técnico"): it's an operational endpoint scraped by infrastructure
(Prometheus), not a versioned business resource.

Deliberately unauthenticated — same criterion already applied to the host
DL training runner in EPIC-2: the only protection is the `127.0.0.1`
network binding on the `backend` container in `docker-compose.yml`. No PII
or clinical data is exposed here, only aggregated counters/histograms.

Multiprocess mode: when `PROMETHEUS_MULTIPROC_DIR` is set (see
`app.core.metrics` for why — the Celery `worker` container records CNN3D
metrics in a separate OS process from this one), this endpoint must build
a fresh `CollectorRegistry` and register `multiprocess.MultiProcessCollector`
on it rather than reading `prometheus_client`'s default global registry,
per the library's own documented pattern for WSGI/ASGI apps in multiprocess
mode (https://prometheus.github.io/client_python/multiprocess/) — the
default registry only ever holds this process's own (backend/uvicorn) data.
"""
import os

from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest, multiprocess

router = APIRouter()


@router.get("/metrics")
def metrics() -> Response:
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        data = generate_latest(registry)
    else:
        data = generate_latest()
    return Response(data, media_type=CONTENT_TYPE_LATEST)
