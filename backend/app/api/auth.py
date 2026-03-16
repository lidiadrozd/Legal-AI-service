# backend/app/api/auth.py - Роутер авторизации
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta

from app.api.deps import get_db
from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token
from app.crud.user import user
from app.schemas.auth import Token, LoginRequest
from app.schemas.user import UserCreate, Consent

router = APIRouter()

@router.post("/register", response_model=Token)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    db_user = user.get_by_email(db, email=user_in.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    new_user = user.create(db, obj_in=user_in)
    access_token = create_access_token(data={"sub": new_user.email})
    refresh_token = create_refresh_token(data={"sub": new_user.email})
    
    return Token(access_token=access_token, refresh_token=refresh_token)

@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user_obj = user.authenticate(db, email=form_data.username, password=form_data.password)
    if not user_obj:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": user_obj.email})
    refresh_token = create_refresh_token(data={"sub": user_obj.email})
    
    return Token(access_token=access_token, refresh_token=refresh_token)

@router.post("/refresh")
def refresh_token(refresh_token_str: str):
    payload = verify_token(refresh_token_str)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    access_token = create_access_token(data={"sub": payload["sub"]})
    return {"access_token": access_token}

@router.post("/consent")
def give_consent(
    consent_in: Consent,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not consent_in.consent:
        raise HTTPException(status_code=400, detail="Consent must be accepted")
    
    user.update(db, db_obj=current_user, obj_in=UserUpdate(consent_given=True))
    return {"message": "Consent accepted"}
