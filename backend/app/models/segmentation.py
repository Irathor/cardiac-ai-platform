import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import GUID
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.biomarker_measurement import BiomarkerMeasurement
    from app.models.image_series import ImageSeries


class Segmentation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A voxel label mask for one ImageSeries.

    `model_version` is null for a manually-uploaded or ground-truth mask (all
    that exists until Phase 5 adds real model inference) and will reference an
    MLflow-registered model version once AIAnalysis exists.
    """

    __tablename__ = "segmentations"

    image_series_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("image_series.id"), index=True
    )
    storage_key: Mapped[str] = mapped_column(String(500))
    model_version: Mapped[str | None] = mapped_column(String(200))
    created_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("users.id"))

    image_series: Mapped["ImageSeries"] = relationship(back_populates="segmentations")
    biomarker_measurements: Mapped[list["BiomarkerMeasurement"]] = relationship(
        back_populates="segmentation"
    )
