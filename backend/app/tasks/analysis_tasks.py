import uuid

from app.celery_app import celery_app
from app.db import session as db_session
from app.services import analysis_service


@celery_app.task(name="app.tasks.analysis_tasks.run_analysis")
def run_analysis(analysis_id: str) -> None:
    """Runs in the Celery worker process, with its own DB session — the
    request/response path only ever enqueues this (see
    app.services.analysis_service.create_analysis).

    Looked up as `db_session.get_session_factory` (module attribute, not a
    bound import) so tests can monkeypatch it to the in-memory test engine —
    see tests/conftest.py's `client` fixture."""
    session_factory = db_session.get_session_factory()
    db = session_factory()
    try:
        analysis_service.execute_analysis(db, analysis_id=uuid.UUID(analysis_id))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
