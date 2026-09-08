"""Login, token issuance/rotation and logout. Business rules live here —
routers only translate between HTTP and these calls (see docs/architecture.md)."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core import security
from app.core.config import get_settings
from app.core.security import TokenType
from app.models.mixins import ensure_utc
from app.models.user import User
from app.repositories import audit_repository, refresh_token_repository, user_repository


class InvalidCredentialsError(Exception):
    pass


class AccountLockedError(Exception):
    pass


class AccountInactiveError(Exception):
    pass


class InvalidRefreshTokenError(Exception):
    pass


def authenticate(db: Session, *, email: str, password: str, ip_address: str | None) -> User:
    """Verifies credentials, enforcing lockout after repeated failures.

    Every outcome (success, bad password, locked, inactive, unknown email) is
    audited. The response given to the caller intentionally does not
    distinguish "unknown email" from "wrong password" (both raise
    InvalidCredentialsError) to avoid leaking which emails are registered.
    """
    settings = get_settings()
    user = user_repository.get_by_email(db, email)

    if user is None:
        audit_repository.record(
            db, user_id=None, action="login", resource_type="user",
            resource_id=None, result="failure", ip_address=ip_address,
            event_metadata={"reason": "unknown_email"},
        )
        raise InvalidCredentialsError()

    if not user.is_active:
        audit_repository.record(
            db, user_id=user.id, action="login", resource_type="user",
            resource_id=str(user.id), result="failure", ip_address=ip_address,
            event_metadata={"reason": "inactive"},
        )
        raise AccountInactiveError()

    if user.is_locked:
        audit_repository.record(
            db, user_id=user.id, action="login", resource_type="user",
            resource_id=str(user.id), result="failure", ip_address=ip_address,
            event_metadata={"reason": "locked"},
        )
        raise AccountLockedError()

    if not security.verify_password(password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.max_failed_login_attempts:
            user.locked_until = datetime.now(timezone.utc) + timedelta(
                minutes=settings.account_lockout_minutes
            )
        db.flush()
        audit_repository.record(
            db, user_id=user.id, action="login", resource_type="user",
            resource_id=str(user.id), result="failure", ip_address=ip_address,
            event_metadata={"reason": "bad_password", "attempts": user.failed_login_attempts},
        )
        raise InvalidCredentialsError()

    user.failed_login_attempts = 0
    user.locked_until = None
    db.flush()
    audit_repository.record(
        db, user_id=user.id, action="login", resource_type="user",
        resource_id=str(user.id), result="success", ip_address=ip_address,
    )
    return user


def issue_tokens(db: Session, user: User) -> tuple[str, str]:
    settings = get_settings()
    access_token = security.create_access_token(user.id)
    raw_refresh_token = security.create_refresh_token(user.id)
    refresh_token_repository.create(
        db,
        user_id=user.id,
        raw_token=raw_refresh_token,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days),
    )
    return access_token, raw_refresh_token


def refresh_tokens(db: Session, raw_refresh_token: str, *, ip_address: str | None) -> tuple[str, str]:
    """Rotates a refresh token: the old one is revoked and a new pair is
    issued. Presenting a token that was already revoked/rotated is treated as
    a possible theft signal and revokes every session for that user."""
    try:
        payload = security.decode_token(raw_refresh_token, TokenType.REFRESH)
    except security.InvalidTokenError as exc:
        raise InvalidRefreshTokenError(str(exc)) from exc

    stored = refresh_token_repository.get_by_raw_token(db, raw_refresh_token)
    user_id = uuid.UUID(payload["sub"])

    if stored is None:
        raise InvalidRefreshTokenError("unknown refresh token")

    if stored.revoked_at is not None or ensure_utc(stored.expires_at) < datetime.now(timezone.utc):
        refresh_token_repository.revoke_all_for_user(db, user_id)
        audit_repository.record(
            db, user_id=user_id, action="refresh_token_reuse_detected",
            resource_type="refresh_token", resource_id=str(stored.id),
            result="failure", ip_address=ip_address,
        )
        raise InvalidRefreshTokenError("token already used or expired")

    user = user_repository.get_by_id(db, user_id)
    if user is None or not user.is_active:
        raise InvalidRefreshTokenError("user no longer active")

    new_access_token = security.create_access_token(user.id)
    new_raw_refresh_token = security.create_refresh_token(user.id)
    settings = get_settings()
    new_stored = refresh_token_repository.create(
        db,
        user_id=user.id,
        raw_token=new_raw_refresh_token,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days),
    )
    refresh_token_repository.revoke(db, stored, replaced_by_id=new_stored.id)
    return new_access_token, new_raw_refresh_token


def logout(db: Session, raw_refresh_token: str) -> None:
    stored = refresh_token_repository.get_by_raw_token(db, raw_refresh_token)
    if stored is not None and stored.revoked_at is None:
        refresh_token_repository.revoke(db, stored)
        audit_repository.record(
            db, user_id=stored.user_id, action="logout", resource_type="refresh_token",
            resource_id=str(stored.id), result="success", ip_address=None,
        )
