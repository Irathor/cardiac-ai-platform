import uuid
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import GUID
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.model_version import ModelVersion


class ModelEvaluation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Metrics for a ModelVersion on one dataset split — always TEST for a
    run produced by app.tasks.training_tasks (see docs/data-dictionary.md;
    the split reserved for a final, unbiased read on performance).

    `accuracy` is nullable because not every model type reports one the same
    way — a U-Net evaluation stores its headline test mean Dice score here
    instead (still the "how good is this model" scalar this column is for),
    and `metrics` always carries the full validation JSON regardless.
    """

    __tablename__ = "model_evaluations"

    model_version_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("model_versions.id"), index=True)
    split: Mapped[str] = mapped_column(String(20))
    accuracy: Mapped[float | None] = mapped_column(Float())
    metrics: Mapped[dict] = mapped_column(JSON())

    model_version: Mapped["ModelVersion"] = relationship(back_populates="evaluations")
