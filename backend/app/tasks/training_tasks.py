import uuid

from app.celery_app import celery_app
from app.db import session as db_session
from app.services import training_service


@celery_app.task(name="app.tasks.training_tasks.run_training")
def run_training(training_run_id: str) -> None:
    """Runs in the Celery worker process, with its own DB session — the
    request/response path only ever enqueues this (see
    app.services.training_service.create_training_run)."""
    session_factory = db_session.get_session_factory()
    db = session_factory()
    try:
        training_service.execute_training(db, training_run_id=uuid.UUID(training_run_id))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
