import uuid

from app.celery_app import celery_app
from app.core.enums import TrainingModelType
from app.db import session as db_session
from app.repositories import training_repository
from app.services import training_service


@celery_app.task(name="app.tasks.training_tasks.run_training")
def run_training(training_run_id: str) -> None:
    """Runs in the Celery worker process, with its own DB session — the
    request/response path only ever enqueues this (see
    app.services.training_service.create_training_run). Dispatches on the
    run's model_type: NEAREST_CENTROID trains in-process (execute_training,
    unchanged), the two DL model types instead drive the host GPU runner
    (execute_dl_training, see docs/dl-training-runner.md)."""
    run_id = uuid.UUID(training_run_id)
    session_factory = db_session.get_session_factory()
    db = session_factory()
    try:
        run = training_repository.get_by_id(db, run_id)
        model_type = run.model_type if run is not None else TrainingModelType.NEAREST_CENTROID.value
        if model_type == TrainingModelType.NEAREST_CENTROID.value:
            training_service.execute_training(db, training_run_id=run_id)
        else:
            training_service.execute_dl_training(db, training_run_id=run_id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
