"""Pure data access for User/Role/UserRole — no business rules here (those
live in app.services.*). Every read excludes soft-deleted rows by default."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole


def get_by_email(db: Session, email: str) -> User | None:
    stmt = select(User).where(User.email == email, User.deleted_at.is_(None))
    return db.execute(stmt).scalar_one_or_none()


def get_by_id(db: Session, user_id: uuid.UUID) -> User | None:
    stmt = select(User).where(User.id == user_id, User.deleted_at.is_(None))
    return db.execute(stmt).scalar_one_or_none()


def list_active(db: Session) -> list[User]:
    stmt = select(User).where(User.deleted_at.is_(None)).order_by(User.full_name)
    return list(db.execute(stmt).scalars())


def create(
    db: Session,
    *,
    organization_id: uuid.UUID,
    email: str,
    full_name: str,
    password_hash: str,
    created_by: uuid.UUID | None = None,
) -> User:
    user = User(
        organization_id=organization_id,
        email=email,
        full_name=full_name,
        password_hash=password_hash,
        created_by=created_by,
    )
    db.add(user)
    db.flush()
    return user


def get_role_by_name(db: Session, name: str) -> Role | None:
    stmt = select(Role).where(Role.name == name)
    return db.execute(stmt).scalar_one_or_none()


def assign_role(db: Session, *, user_id: uuid.UUID, role_id: uuid.UUID, assigned_by: uuid.UUID | None) -> None:
    existing = db.execute(
        select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role_id)
    ).scalar_one_or_none()
    if existing is not None:
        return
    db.add(UserRole(user_id=user_id, role_id=role_id, assigned_by=assigned_by))
    db.flush()
