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
