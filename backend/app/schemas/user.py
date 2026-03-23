# backend/app/schemas/user.py
from pydantic import BaseModel, EmailStr
from typing import Optional

class UserBase(BaseModel):
    email: EmailStr
    full_name: str

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    is_active: Optional[bool] = True
    consent_given: Optional[bool] = None

class UserInDB(UserBase):
    id: int
    hashed_password: str
    is_active: bool
    is_superuser: bool = False
    consent_given: bool = False

    class Config:
        from_attributes = True

class User(UserBase):
    id: int
    is_active: bool
    is_superuser: bool
    consent_given: bool

    class Config:
        from_attributes = True

class Consent(BaseModel):
    consent: bool


class UserPublic(BaseModel):
    """Ответ API в формате, ожидаемом фронтендом."""

    id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    is_consent_given: bool
    created_at: str


def user_to_public(u) -> UserPublic:
    ca = getattr(u, "created_at", None)
    created = ca.isoformat() if ca is not None else "1970-01-01T00:00:00+00:00"
    return UserPublic(
        id=str(u.id),
        email=u.email,
        full_name=u.full_name,
        role="super_admin" if u.is_superuser else "user",
        is_active=u.is_active,
        is_consent_given=u.consent_given,
        created_at=created,
    )
