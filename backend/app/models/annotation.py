import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import AnnotationStatus
from app.db.base import Base
from app.db.types import GUID
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.segmentation import Segmentation


class Annotation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A correction/review task on an existing Segmentation, assigned to one
    ANNOTATOR (see docs/permissions.md — "View only assigned annotation
    cases"). Draft until submitted for review; a DOCTOR then approves it into
    ground truth or rejects it back to the annotator (see
    docs/data-dictionary.md). Only an APPROVED annotation can be selected
    into a DatasetCase.
    """

    __tablename__ = "annotations"

    based_on_segmentation_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("segmentations.id"), index=True
    )
    annotator_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"), index=True)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default=AnnotationStatus.DRAFT.value, index=True)

    # Set once the annotator uploads a corrected mask (stored as an ordinary
    # Segmentation row with model_version="manual-correction").
    corrected_segmentation_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("segmentations.id")
    )
    diagnosis_label: Mapped[str | None] = mapped_column(String(100))

    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("users.id"))
    review_comment: Mapped[str | None] = mapped_column(String(2000))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    based_on_segmentation: Mapped["Segmentation"] = relationship(foreign_keys=[based_on_segmentation_id])
    corrected_segmentation: Mapped["Segmentation | None"] = relationship(
        foreign_keys=[corrected_segmentation_id]
    )
