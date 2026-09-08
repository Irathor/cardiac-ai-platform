"""FastAPI dependencies for authentication and role-based authorization.

Every protected route depends on `get_current_user` (or `require_roles`), and
this is the *only* place that is allowed to be authoritative about it — the
frontend may hide a button, but the API must reject the request itself (see
docs/permissions.md).
"""
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import InvalidTokenError, TokenType, decode_token
from app.db.session import get_db
from app.models.user import User
from app.repositories import user_repository

_bearer_scheme = HTTPBearer(auto_error=True)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = decode_token(credentials.credentials, TokenType.ACCESS)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
        ) from exc

    user = user_repository.get_by_id(db, uuid.UUID(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer active"
        )
    return user


def require_roles(*allowed_roles: str):
    """Returns a dependency that 403s unless the current user holds at least
    one of `allowed_roles`. Role names must come from app.core.roles.RoleName."""

    def _check(current_user: User = Depends(get_current_user)) -> User:
        if not current_user.role_names.intersection(allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return current_user

    return _check
