"""
Legal AI Service - Главный файл FastAPI
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager  # ✅ ИСПРАВЛЕНО!

from app.api import auth, chat  # Импорты из __init__.py
from app.db.session import engine  # ✅ Правильный импорт
from app.db.base_class import Base  # ✅ Правильный импорт
from app.core.config import settings

# 🔥 Создаем таблицы ПРИ СТАРТЕ (один раз)
Base.metadata.create_all(bind=engine)
print("✅ База данных инициализирована")

@asynccontextmanager  # ✅ Правильный синтаксис
async def lifespan(app: FastAPI):
    print("🚀 Starting Legal AI Service...")
    print(f"📊 Config: {settings.APP_NAME} v{settings.VERSION}")
    print(f"🔑 GigaChat: {'✅ Ready' if settings.GIGACHAT_CLIENT_ID else '❌ Setup .env'}")
    yield
    print("🛑 Shutting down...")

app = FastAPI(
    title="Legal AI Service 🚀",
    description="Юридический ИИ-ассистент (GigaChat + RAG)",
    version="1.0.0",
    lifespan=lifespan  # ✅ Правильное использование
)

# CORS для фронтенда
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # settings.CORS_ORIGINS в проде
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Роутеры
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(chat.router, prefix="/chat", tags=["chat"])

@app.get("/")
async def root():
    return {
        "message": "Legal AI Service 🚀",
        "version": settings.VERSION,
        "status": "running",
        "endpoints": {
            "auth": ["/auth/register", "/auth/login"],
            "chat": ["/chat/new", "/chat/list", "/chat/{id}/send_stream"],
            "docs": "/docs"
        },
        "gigachat": settings.GIGACHAT_CLIENT_ID[:20] + "..." if settings.GIGACHAT_CLIENT_ID else "Not configured"
    }

@app.get("/health")
async def health():
    return {"status": "healthy", "service": settings.APP_NAME}

@app.get("/config")
async def config_info():
    return {
        "app_name": settings.APP_NAME,
        "debug": settings.DEBUG,
        "gigachat_ready": bool(settings.GIGACHAT_CLIENT_ID and settings.GIGACHAT_CLIENT_SECRET),
        "db_url": settings.DATABASE_URL.split("@")[1] if settings.DATABASE_URL else None
    }
