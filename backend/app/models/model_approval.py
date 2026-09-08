import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import GUID
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.model_version import ModelVersion


class ModelApproval(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A MODEL_APPROVER's decision on a ModelVersion. `justification` is
    mandatory (see docs/permissions.md: "MODEL_APPROVER always records a
    mandatory justification for approval/activation/rollback") — enforced in
    app.services.model_service, not just left to the client to bother with.
    """

    __tablename__ = "model_approvals"

    model_version_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("model_versions.id"), index=True)
    approver_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(20))
    justification: Mapped[str] = mapped_column(String(2000))

    model_version: Mapped["ModelVersion"] = relationship(back_populates="approvals")
