import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent


def record(
    db: Session,
    *,
    user_id: uuid.UUID | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    result: str,
    ip_address: str | None = None,
    event_metadata: dict | None = None,
) -> AuditEvent:
    """Appends one audit event. There is intentionally no update/delete here —
    the audit trail is write-once (see docs/permissions.md)."""
    event = AuditEvent(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        result=result,
        ip_address=ip_address,
        event_metadata=event_metadata,
    )
    db.add(event)
    db.flush()
    return event


def list_recent(db: Session, limit: int = 100) -> list[AuditEvent]:
    stmt = select(AuditEvent).order_by(AuditEvent.occurred_at.desc()).limit(limit)
    return list(db.execute(stmt).scalars())
