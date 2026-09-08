import uuid

from pydantic import BaseModel, EmailStr


class UserOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    is_active: bool
    roles: list[str]

    model_config = {"from_attributes": True}


class UserCreateRequest(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    roles: list[str] = []


class UserUpdateRequest(BaseModel):
    full_name: str | None = None
    is_active: bool | None = None
    roles: list[str] | None = None
