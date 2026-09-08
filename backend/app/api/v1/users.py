import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_roles
from app.core.roles import RoleName
from app.db.session import get_db
from app.models.user import User
from app.repositories import user_repository
from app.schemas.user import UserCreateRequest, UserOut, UserUpdateRequest
from app.services import user_service

router = APIRouter()


def _to_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        roles=sorted(user.role_names),
    )


@router.get("/me", response_model=UserOut)
def read_me(current_user: User = Depends(get_current_user)) -> UserOut:
    return _to_out(current_user)


@router.get("", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_roles(RoleName.ADMIN)),
) -> list[UserOut]:
    return [_to_out(u) for u in user_repository.list_active(db)]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(RoleName.ADMIN)),
) -> UserOut:
    try:
        user = user_service.create_user(
            db,
            organization_id=admin.organization_id,
            email=payload.email,
            full_name=payload.full_name,
            password=payload.password,
            roles=payload.roles,
            created_by=admin.id,
        )
    except user_service.RoleNotFoundError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown role: {exc}"
        ) from exc
    db.commit()
    db.refresh(user)
    return _to_out(user)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(RoleName.ADMIN)),
) -> UserOut:
    user = user_repository.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.is_active is not None:
        user_service.set_active(db, user=user, is_active=payload.is_active, actor_id=admin.id)
    if payload.roles is not None:
        try:
            user_service.replace_roles(db, user=user, role_names=payload.roles, actor_id=admin.id)
        except user_service.RoleNotFoundError as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown role: {exc}"
            ) from exc

    db.commit()
    db.refresh(user)
    return _to_out(user)
