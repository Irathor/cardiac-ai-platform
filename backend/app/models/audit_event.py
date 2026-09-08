import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import GUID
from app.models.mixins import _utcnow


class AuditEvent(Base):
    """Append-only audit trail. No service or router may update or delete a
    row here — see docs/permissions.md (auditor role is read-only too)."""

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100), index=True)
    resource_type: Mapped[str] = mapped_column(String(100))
    resource_id: Mapped[str | None] = mapped_column(String(100))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    result: Mapped[str] = mapped_column(String(20))  # "success" | "failure"
    ip_address: Mapped[str | None] = mapped_column(String(64))
    # Non-sensitive context only — never clinical data (see docs/clinical-limitations.md
    # and the platform-wide rule against logging patient information).
    event_metadata: Mapped[dict | None] = mapped_column(JSON)
