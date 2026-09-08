import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import GUID
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.segmentation import Segmentation


class BiomarkerMeasurement(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One named value computed from a Segmentation (see ml.cardiac_ai_ml.biomarkers).

    Modeled as name/value/unit rows rather than fixed columns per biomarker so
    adding a new biomarker never requires a migration that leaves existing
    rows with an always-null column (see docs/data-dictionary.md).
    """

    __tablename__ = "biomarker_measurements"

    segmentation_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("segmentations.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(100), index=True)
    value: Mapped[float] = mapped_column(Float())
    unit: Mapped[str] = mapped_column(String(20))

    segmentation: Mapped["Segmentation"] = relationship(back_populates="biomarker_measurements")
