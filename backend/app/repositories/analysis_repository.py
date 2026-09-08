import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ai_analysis import AIAnalysis


def get_by_id(db: Session, analysis_id: uuid.UUID) -> AIAnalysis | None:
    stmt = select(AIAnalysis).where(AIAnalysis.id == analysis_id)
    return db.execute(stmt).scalar_one_or_none()


def list_for_study(db: Session, imaging_study_id: uuid.UUID) -> list[AIAnalysis]:
    stmt = (
        select(AIAnalysis)
        .where(AIAnalysis.imaging_study_id == imaging_study_id)
        .order_by(AIAnalysis.created_at.desc())
    )
    return list(db.execute(stmt).scalars())


def create(db: Session, *, imaging_study_id: uuid.UUID, requested_by: uuid.UUID | None, **fields) -> AIAnalysis:
    analysis = AIAnalysis(imaging_study_id=imaging_study_id, requested_by=requested_by, **fields)
    db.add(analysis)
    db.flush()
    return analysis
