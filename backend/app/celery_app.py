"""Celery app instance — the only place besides app.tasks that imports both
the data-access layer and the ml/ package (see docs/architecture.md): heavy
analysis work must never run inside an HTTP request/response cycle.
"""
from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "cardiac_ai_backend",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.analysis_tasks", "app.tasks.training_tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
)
