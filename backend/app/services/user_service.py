"""User management business rules: creation, activation, and role assignment.
Every mutation is audited — see docs/permissions.md (ADMIN capabilities)."""
import uuid

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import User
from app.repositories import audit_repository, user_repository


class RoleNotFoundError(Exception):
    pass


def _set_roles(db: Session, *, user: User, role_names: list[str], assigned_by: uuid.UUID | None) -> None:
    for name in role_names:
        role = user_repository.get_role_by_name(db, name)
        if role is None:
            raise RoleNotFoundError(name)
        user_repository.assign_role(db, user_id=user.id, role_id=role.id, assigned_by=assigned_by)


def create_user(
    db: Session,
    *,
    organization_id: uuid.UUID,
    email: str,
    full_name: str,
    password: str,
    roles: list[str],
    created_by: uuid.UUID | None,
) -> User:
    user = user_repository.create(
        db,
        organization_id=organization_id,
        email=email,
        full_name=full_name,
        password_hash=hash_password(password),
        created_by=created_by,
    )
    _set_roles(db, user=user, role_names=roles, assigned_by=created_by)
    audit_repository.record(
        db, user_id=created_by, action="user_created", resource_type="user",
        resource_id=str(user.id), result="success",
        event_metadata={"roles": roles},
    )
    return user


def set_active(db: Session, *, user: User, is_active: bool, actor_id: uuid.UUID | None) -> None:
    user.is_active = is_active
    db.flush()
    audit_repository.record(
        db, user_id=actor_id, action="user_activated" if is_active else "user_deactivated",
        resource_type="user", resource_id=str(user.id), result="success",
    )


def replace_roles(db: Session, *, user: User, role_names: list[str], actor_id: uuid.UUID | None) -> None:
    from sqlalchemy import delete

    from app.models.user_role import UserRole

    db.execute(delete(UserRole).where(UserRole.user_id == user.id))
    db.flush()
    _set_roles(db, user=user, role_names=role_names, assigned_by=actor_id)
    db.expire(user, ["user_roles"])  # the in-memory collection is stale after the raw delete()
    audit_repository.record(
        db, user_id=actor_id, action="user_roles_changed", resource_type="user",
        resource_id=str(user.id), result="success", event_metadata={"roles": role_names},
    )
