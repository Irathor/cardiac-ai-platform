import hashlib
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.refresh_token import RefreshToken


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create(db: Session, *, user_id: uuid.UUID, raw_token: str, expires_at: datetime) -> RefreshToken:
    row = RefreshToken(user_id=user_id, token_hash=hash_token(raw_token), expires_at=expires_at)
    db.add(row)
    db.flush()
    return row


def get_by_raw_token(db: Session, raw_token: str) -> RefreshToken | None:
    stmt = select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token))
    return db.execute(stmt).scalar_one_or_none()


def revoke(db: Session, token: RefreshToken, *, replaced_by_id: uuid.UUID | None = None) -> None:
    from datetime import timezone

    token.revoked_at = datetime.now(timezone.utc)
    token.replaced_by_id = replaced_by_id
    db.flush()


def revoke_all_for_user(db: Session, user_id: uuid.UUID) -> None:
    from datetime import timezone

    now = datetime.now(timezone.utc)
    stmt = select(RefreshToken).where(
        RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
    )
    for token in db.execute(stmt).scalars():
        token.revoked_at = now
    db.flush()
