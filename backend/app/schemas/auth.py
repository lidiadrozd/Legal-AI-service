# backend/app/schemas/auth.py
from pydantic import BaseModel

from app.schemas.user import UserPublic


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenWithUser(Token):
    user: UserPublic


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshTokenBody(BaseModel):
    refresh_token: str


class ConsentRequest(BaseModel):
    consent_data_processing: bool
    consent_terms: bool
    consent_ai_usage: bool
