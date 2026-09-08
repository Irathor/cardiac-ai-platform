import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import GUID
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class RefreshToken(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Tracks issued refresh tokens so they can be individually revoked.

    Only a SHA-256 hash of the token is stored — never the raw JWT — so a
    leaked database dump cannot be replayed as a valid session.
    """

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Rotation chain: when a refresh token is used, it is revoked and this
    # points at the token that replaced it — lets us detect reuse of a token
    # that was already rotated away (a signal of token theft).
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(GUID())
