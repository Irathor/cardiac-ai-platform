"""Shared columns required on every clinically-relevant entity (see docs/data-dictionary.md).

Every table that represents a real domain entity (User, Patient, ImagingStudy, ...)
must inherit both mixins so it always carries a stable UUID identity and an
audit-friendly creation/update timestamp, per the platform's data governance rules.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.db.types import GUID


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime) -> datetime:
    """Some DB drivers (notably SQLite) drop tzinfo on read even for a
    timezone-aware column. Every datetime this app writes is already UTC, so
    a naive value read back is always safe to reinterpret as UTC rather than
    the local system timezone."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
