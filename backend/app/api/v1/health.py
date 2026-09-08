"""Liveness/readiness endpoints used by Docker Compose healthchecks and the frontend banner."""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter()


@router.get("/live")
def liveness() -> dict:
    """Process is up. Does not touch the database — used for container liveness probes."""
    return {"status": "ok"}


@router.get("/ready")
def readiness(db: Session = Depends(get_db)) -> dict:
    """Process can actually serve traffic: the database connection is checked."""
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}
