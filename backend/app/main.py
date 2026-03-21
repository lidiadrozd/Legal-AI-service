"""
Legal AI Service - Главный файл FastAPI
🚀 Мониторинг изменений законов + GigaChat RAG
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import engine, get_db
from app.db.base_class import Base
from app.api import auth, chat, admin  # ✅ + admin роутер
from app.core.security import verify_token

# 🔥 Создаем таблицы ПРИ СТАРТЕ (один раз)
Base.metadata.create_all(bind=engine)
print("✅ База данных инициализирована: law_documents, law_changes, users")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events"""
    print("🚀 Starting Legal AI Service...")
    print(f"📊 Config: {settings.APP_NAME} v{settings.VERSION}")
    print(f"🔑 GigaChat: {'✅ Ready' if settings.GIGACHAT_CLIENT_ID else '❌ Setup .env'}")
    print(f"📈 Celery: {'✅ Redis ready' if os.getenv('CELERY_BROKER_URL') else '❌ Redis'}")
    
    # Startup: Celery ping
    try:
        import redis
        r = redis.from_url(settings.CELERY_BROKER_URL)
        r.ping()
        print("✅ Celery Redis: Connected")
    except:
        print("⚠️  Celery Redis: Not ready")
    
    yield
    
    print("🛑 Shutting down Legal AI Service...")

# ✅ FastAPI app с lifespan
app = FastAPI(
    title="Legal AI Service 🚀",
    description="""Юридический ИИ-ассистент с мониторингом изменений законов
- GigaChat RAG (поиск по кодексам)
- Автоматический мониторинг pravo.gov.ru
- Уведомления о изменениях
- JWT авторизация""",
    version="1.0.0",
    lifespan=lifespan
)

# ✅ CORS для фронтенда
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Роутеры (порядок ВАЖЕН!)
app.include_router(auth.router, prefix="/auth", tags=["🔐 Auth"])
app.include_router(chat.router, prefix="/chat", tags=["💬 Chat"])
app.include_router(admin.router, prefix="/admin", tags=["⚙️ Admin"])  # ✅ НОВЫЙ!

# ✅ Health endpoints
@app.get("/", tags=["📊 Status"])
async def root():
    """Главная страница API"""
    return {
        "message": "Legal AI Service 🚀",
        "version": settings.VERSION,
        "status": "running" if settings.GIGACHAT_CLIENT_ID else "config_required",
        "endpoints": {
            "auth": ["/auth/register", "/auth/login"],
            "chat": ["/chat/new", "/chat/list", "/chat/{id}/send_stream"],
            "admin": ["/admin/monitor-laws"],  # ✅ Новый
            "docs": "/docs",
            "flower": "http://localhost:5555"  # Celery UI
        },
        "features": {
            "gigachat": bool(settings.GIGACHAT_CLIENT_ID),
            "celery_monitoring": bool(settings.CELERY_BROKER_URL),
            "pgvector": settings.ENABLE_PGVECTOR,
            "law_monitoring": True
        }
    }

@app.get("/health", tags=["📊 Status"])
async def health():
    """Health check для мониторинга"""
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
        "timestamp": os.getenv("TIMESTAMP", "2026-03-21")
    }

@app.get("/config", tags=["📊 Status"])
async def config_info(request: Request, db: AsyncSession = Depends(get_db)):
    """Конфигурация и статус сервисов"""
    return {
        "app_name": settings.APP_NAME,
        "debug": settings.DEBUG,
        "environment": settings.ENVIRONMENT,
        "gigachat_ready": bool(settings.GIGACHAT_CLIENT_ID and settings.GIGACHAT_CLIENT_SECRET),
        "celery_ready": bool(settings.CELERY_BROKER_URL),
        "db_url": str(settings.DATABASE_URL).split("@")[-1] if settings.DATABASE_URL else None,
        "cors_origins": settings.CORS_ORIGINS,
        "version": settings.VERSION,
        "docs": f"{request.url.path}../docs"
    }

@app.get("/status/law-monitoring", tags=["📊 Status"])
async def law_monitoring_status():
    """Статус мониторинга изменений законов"""
    try:
        from app.models.law_changes import LawChange
        from sqlalchemy import select
        from app.db.session import AsyncSessionLocal
        
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(LawChange).limit(5))
            recent_changes = result.scalars().all()
            
        return {
            "service": "law_monitoring",
            "status": "active",
            "recent_changes": len(recent_changes),
            "last_celery_task": "check /flower для деталей"
        }
    except Exception as e:
        return {"service": "law_monitoring", "status": "initializing", "error": str(e)}

# ✅ 404 handler
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return {"error": "Endpoint not found", "available": ["/", "/docs", "/health"]}

# ✅ 500 handler
@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    return {"error": "Internal server error", "contact": "admin@ai-jurist.ru"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info" if not settings.DEBUG else "debug"
    )
