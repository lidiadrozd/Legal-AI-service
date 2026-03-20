"""
Legal AI Service - Конфигурация приложения
"""
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@db:5432/legal_ai"
    
    # Redis
    REDIS_URL: str = "redis://redis:6379/0"
    
    # JWT Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # AI Services
    GIGACHAT_API_KEY: str
    GIGACHAT_MODEL: str = "GigaChat-Pro"
    TAVILY_API_KEY: Optional[str] = None
    
    # App
    APP_NAME: str = "Legal AI Service"
    DEBUG: bool = False

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()

