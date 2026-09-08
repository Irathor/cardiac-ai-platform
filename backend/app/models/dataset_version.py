import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import DatasetVersionStatus
from app.db.base import Base
from app.db.types import GUID
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.dataset import Dataset
    from app.models.dataset_case import DatasetCase


class DatasetVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Immutable once LOCKED (see docs/phases.md) — `checksum` is a SHA-256
    over the sorted (patient_id, annotation_id, split) triples of every case,
    computed at lock time, so a version's exact case membership can always be
    verified later (e.g. against what a TrainingRun actually consumed)."""

    __tablename__ = "dataset_versions"
    __table_args__ = (UniqueConstraint("dataset_id", "version_number", name="uq_dataset_version_number"),)

    dataset_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("datasets.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer())
    status: Mapped[str] = mapped_column(String(20), default=DatasetVersionStatus.DRAFT.value)
    checksum: Mapped[str | None] = mapped_column(String(64))
    created_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("users.id"))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    dataset: Mapped["Dataset"] = relationship(back_populates="versions")
    cases: Mapped[list["DatasetCase"]] = relationship(back_populates="dataset_version")
