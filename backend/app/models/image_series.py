import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import GUID
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.imaging_study import ImagingStudy
    from app.models.segmentation import Segmentation


class ImageSeries(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One uploaded NIfTI volume belonging to an ImagingStudy.

    `phase` distinguishes end-diastole/end-systole frames of a cine acquisition
    (needed later to pair them for an ejection-fraction calculation) and is
    left null for a study that isn't a paired-phase cine series.
    """

    __tablename__ = "image_series"

    imaging_study_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("imaging_studies.id"), index=True
    )
    series_type: Mapped[str] = mapped_column(String(50), default="CINE_SHORT_AXIS")
    phase: Mapped[str | None] = mapped_column(String(20))

    storage_key: Mapped[str] = mapped_column(String(500))
    voxel_spacing_x_mm: Mapped[float] = mapped_column(Float())
    voxel_spacing_y_mm: Mapped[float] = mapped_column(Float())
    voxel_spacing_z_mm: Mapped[float] = mapped_column(Float())
    shape_x: Mapped[int] = mapped_column(Integer())
    shape_y: Mapped[int] = mapped_column(Integer())
    shape_z: Mapped[int] = mapped_column(Integer())

    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("users.id"))

    imaging_study: Mapped["ImagingStudy"] = relationship()
    segmentations: Mapped[list["Segmentation"]] = relationship(back_populates="image_series")
