"""
Legal AI Service — Полная конфигурация Pydantic v2
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional
from functools import lru_cache
import os

class Settings(BaseSettings):
    # ========================================
    # DATABASE & CACHE
    # ========================================
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@db:5432/legal_ai"
    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"
    
    # ========================================
    # JWT SECURITY
    # ========================================
    SECRET_KEY: str = os.getenv('SECRET_KEY', "dev-super-secret-change-in-production!")  # ✅ Дефолт!
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    SUPERADMIN_EMAIL: str = os.getenv("SUPERADMIN_EMAIL", "")
    SUPERADMIN_PASSWORD: str = os.getenv("SUPERADMIN_PASSWORD", "")
    SUPERADMIN_FULL_NAME: str = os.getenv("SUPERADMIN_FULL_NAME", "Super Admin")
    
    # ========================================
    # GigaChat API (автообновление токена)
    # ========================================
    GIGACHAT_CLIENT_ID: str = os.getenv('GIGACHAT_CLIENT_ID', "")  # ✅ Дефолт!
    GIGACHAT_CLIENT_SECRET: str = os.getenv('GIGACHAT_CLIENT_SECRET', "")  # ✅ Дефолт!
    GIGACHAT_MODEL: str = "GigaChat-Pro"
    GIGACHAT_SCOPE: str = "GIGACHAT_API_PERS"
    # Таймаут ожидания полного ответа модели в чате (сек.)
    GIGACHAT_GENERATE_TIMEOUT_SECONDS: int = 120
    
    # ========================================
    # RAG & Vector Store
    # ========================================
    RAG_DOCS_PATH: str = "/app/rag_docs"
    EMBEDDING_MODEL: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    VECTOR_DB_TYPE: str = "pgvector"
    ENABLE_PGVECTOR: bool = True  # ✅ Обязательно!
    
    # ========================================
    # APP SETTINGS
    # ========================================
    APP_NAME: str = "Legal AI Service"
    DEBUG: bool = True  # ✅ True для разработки!
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    
    # ========================================
    # API & CORS
    # ========================================
    API_V1_STR: str = "/api/v1"
    CORS_ORIGINS: List[str] = ["*"]
    
    # ========================================
    # Rate Limiting
    # ========================================
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW: int = 3600
    
    # ========================================
    # CELERY
    # ========================================
    CELERY_TASK_ALWAYS_EAGER: bool = False
    CELERY_TASK_TIME_LIMIT: int = 300

    # ========================================
    # Документы (файлы пользователей + встроенные шаблоны)
    # ========================================
    DOCUMENTS_STORAGE_PATH: str = "storage/documents"
    # Пустая строка = каталог backend/builtin_templates относительно корня проекта backend
    BUILTIN_TEMPLATES_PATH: str = ""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=False  # ✅ debug = DEBUG!
    )

@lru_cache()
def get_settings() -> Settings:
    """Кэшированная конфигурация"""
    return Settings()

# ✅ Глобальный экземпляр
settings = get_settings()
