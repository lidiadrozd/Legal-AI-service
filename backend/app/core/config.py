
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional
from functools import lru_cache

class Settings(BaseSettings):
    # ========================================
    # DATABASE & CACHE
    # ========================================
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@db:5432/legal_ai"
    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/1"      # ✅ ДОБАВЛЕНО!
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"  # ✅ ДОБАВЛЕНО!
    
    # ========================================
    # JWT SECURITY
    # ========================================
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # ========================================
    # GigaChat API (автообновление токена)
    # ========================================
    GIGACHAT_CLIENT_ID: str           # Из developers.sber.ru
    GIGACHAT_CLIENT_SECRET: str       # Из developers.sber.ru  
    GIGACHAT_MODEL: str = "GigaChat-Pro"
    GIGACHAT_SCOPE: str = "GIGACHAT_API_PERS"
    
    # ========================================
    # RAG & Vector Store
    # ========================================
    RAG_DOCS_PATH: str = "/app/rag_docs"
    EMBEDDING_MODEL: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    VECTOR_DB_TYPE: str = "pgvector"  # или "faiss"
    ENABLE_PGVECTOR: bool = True      # ✅ ИСПРАВЛЕНИЕ ПРОБЛЕМЫ 4!
    
    # ========================================
    # APP SETTINGS
    # ========================================
    APP_NAME: str = "Legal AI Service"
    DEBUG: bool = False
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"  # ✅ ДОБАВЛЕНО! (dev/production)
    
    # ========================================
    # API & CORS
    # ========================================
    API_V1_STR: str = "/api/v1"
    CORS_ORIGINS: List[str] = ["*"]   # ✅ List[str] вместо str!
    
    # ========================================
    # Rate Limiting (Redis)
    # ========================================
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW: int = 3600  # 1 час
    
    # ========================================
    # CELERY
    # ========================================
    CELERY_TASK_ALWAYS_EAGER: bool = False  # ✅ Для main.py
    CELERY_TASK_TIME_LIMIT: int = 300
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=False  # ✅ Не чувствительно к регистру
    )

@lru_cache()
def get_settings() -> Settings:
    """Кэшированная конфигурация (один экземпляр)"""
    return Settings()

# Глобальный экземпляр (FastAPI стиль)
settings = get_settings()
