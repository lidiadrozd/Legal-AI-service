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
    GIGACHAT_MODEL: str = "GigaChat"
    GIGACHAT_SCOPE: str = "GIGACHAT_API_B2B"
    GIGACHAT_PRICE_PER_1K_TOKENS: float = 0.065

    # ========================================
    # SaluteSpeech (распознавание речи)
    # ========================================
    SALUTE_SPEECH_CLIENT_ID: str = os.getenv("SALUTE_SPEECH_CLIENT_ID", "")
    SALUTE_SPEECH_CLIENT_SECRET: str = os.getenv("SALUTE_SPEECH_CLIENT_SECRET", "")
    # SALUTE_SPEECH_PERS — физлица; SALUTE_SPEECH_CORP / B2B — по договору в кабинете Сбера
    SALUTE_SPEECH_SCOPE: str = os.getenv("SALUTE_SPEECH_SCOPE", "SALUTE_SPEECH_PERS")
    SALUTE_SPEECH_SAMPLE_RATE: int = int(os.getenv("SALUTE_SPEECH_SAMPLE_RATE", "16000"))
    
    # ========================================
    # RAG & Vector Store
    # ========================================
    RAG_DOCS_PATH: str = "/app/rag_docs"
    DOCUMENTS_STORAGE_DIR: str = "/app/storage/documents"
    OCR_LANGS: str = os.getenv("OCR_LANGS", "rus+eng")
    OCR_MAX_PDF_PAGES: int = int(os.getenv("OCR_MAX_PDF_PAGES", "15"))
    EMBEDDING_MODEL: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    VECTOR_DB_TYPE: str = "pgvector"
    ENABLE_PGVECTOR: bool = True  # ✅ Обязательно!
    RAG_ENABLED: bool = True
    RAG_VECTOR_TOP_K: int = 3
    RAG_RERANK_THRESHOLD: float = 0.7
    RAG_MAX_CONTEXT_CHUNKS: int = 2
    RAG_CHUNK_MAX_CHARS: int = 2000

    # ========================================
    # Chat response cache
    # ========================================
    CHAT_RESPONSE_CACHE_ENABLED: bool = True
    CHAT_RESPONSE_CACHE_TTL_SECONDS: int = 86400
    CHAT_RESPONSE_CACHE_HISTORY_CHARS: int = 6000
    
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
    # SMTP / Email
    # ========================================
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.yandex.ru")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM: str = os.getenv("SMTP_FROM", "")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")

    # ========================================
    # CELERY
    # ========================================
    CELERY_TASK_ALWAYS_EAGER: bool = False
    CELERY_TASK_TIME_LIMIT: int = 300
    LAW_CHANGE_SOURCES: str = "https://www.consultant.ru/law/review/fed/updprof/"
    LAW_CHANGE_HTTP_TIMEOUT: int = 30
    LAW_CHANGE_MAX_CATEGORIES: int = 40

    def law_change_source_list(self) -> list[str]:
        return [item.strip() for item in self.LAW_CHANGE_SOURCES.split(",") if item.strip()]
    
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
