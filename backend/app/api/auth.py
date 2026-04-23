# backend/app/api/auth.py - Роутер авторизации
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.security import create_access_token, create_refresh_token, verify_token
from app.crud.user import user
from app.schemas.auth import (
    TokenWithUser,
    LoginRequest,
    RefreshTokenBody,
    ConsentRequest,
)
from app.schemas.user import UserCreate, UserUpdate, UserPublic, user_to_public
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["🔐 Auth"])


def _tokens_for_user(db_user: User) -> TokenWithUser:
    access_token = create_access_token(data={"sub": db_user.email})
    refresh_token = create_refresh_token(data={"sub": db_user.email})
    return TokenWithUser(
        access_token=access_token,
        refresh_token=refresh_token,
        user=user_to_public(db_user),
    )


@router.post("/register", response_model=TokenWithUser)
async def register(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    db_user = await user.get_by_email(db, email=user_in.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = await user.create(db, obj_in=user_in)
    return _tokens_for_user(new_user)


@router.post("/login", response_model=TokenWithUser)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    user_obj = await user.authenticate(
        db, email=body.email, password=body.password
    )
    if not user_obj:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return _tokens_for_user(user_obj)


@router.post("/refresh")
async def refresh_token_endpoint(body: RefreshTokenBody):
    payload = verify_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    access_token = create_access_token(data={"sub": payload["sub"]})
    return {"access_token": access_token}


@router.get("/me", response_model=UserPublic)
async def get_me(current_user: User = Depends(get_current_user)):
    return user_to_public(current_user)


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user)):
    return {"message": "ok"}


@router.post("/consent")
async def give_consent(
    consent_in: ConsentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not (
        consent_in.consent_data_processing
        and consent_in.consent_terms
        and consent_in.consent_ai_usage
    ):
        raise HTTPException(status_code=400, detail="Consent must be accepted")

    await user.update(
        db, db_obj=current_user, obj_in=UserUpdate(consent_given=True)
    )
    return {"message": "Consent accepted"}
