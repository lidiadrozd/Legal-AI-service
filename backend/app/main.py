"""
Legal AI Service - Главный файл FastAPI
"""
import os
from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import AsyncSession

# ✅ ИМПОРТЫ
from app.core.config import settings
from app.core.superadmin import ensure_superadmin_exists
from app.db.session import engine, get_db, AsyncSessionLocal
from app.db.base_class import Base
from app import models  # noqa: F401 - регистрирует модели в metadata

from app.api import auth, chat, admin, court_filings, notifications, ws_notifications

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """✅ АСИНХРОННЫЙ Lifecycle"""
    
    # 🔥 АСИНХРОННАЯ ИНИЦИАЛИЗАЦИЯ БД
    print("🔄 Инициализация базы данных...")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("✅ База данных инициализирована АСИНХРОННО!")
    except Exception as e:
        print(f"❌ Ошибка БД: {e}")

    # Автосоздание суперадмина из переменных окружения.
    async with AsyncSessionLocal() as db:
        created = await ensure_superadmin_exists(db)
        if created:
            print("✅ Superadmin user created")
    
    # ✅ Проверка конфигурации
    print("🚀 Starting Legal AI Service...")
    print(f"📊 Config: {settings.APP_NAME} v{settings.VERSION}")
    print(f"🔑 GigaChat: {'✅ Ready' if settings.GIGACHAT_CLIENT_ID else '❌ Setup .env'}")
    print(f"📈 Celery: {'✅ Redis ready' if settings.CELERY_BROKER_URL else '❌ Redis'}")
    print(f"🧠 pgvector: {'✅ Enabled' if getattr(settings, 'ENABLE_PGVECTOR', False) else '❌ Disabled'}")
    
    # ✅ Celery Redis ping (безопасно)
    try:
        import redis
        r = redis.from_url(settings.CELERY_BROKER_URL)
        r.ping()
        print("✅ Celery Redis: Connected")
    except:
        print("⚠️  Celery Redis: Not ready (но API работает!)")
    
    yield
    
    # ✅ Закрытие соединений
    await engine.dispose()
    print("🛑 Legal AI Service остановлен")

# ✅ FastAPI app
app = FastAPI(
    title="Legal AI Service 🚀",
    description="""Юридический ИИ-ассистент с мониторингом изменений законов
- GigaChat RAG (поиск по кодексам)
- Автоматический мониторинг pravo.gov.ru
- Уведомления о изменениях
- JWT авторизация""",
    version="1.0.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan
)

# ✅ CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(admin.router)
app.include_router(court_filings.router)
app.include_router(notifications.router)
app.include_router(ws_notifications.router)

# ✅ Health endpoints
@app.get("/", tags=["📊 Status"])
async def root():
    """Главная страница API"""
    return {
        "message": "Legal AI Service 🚀",
        "version": settings.VERSION,
        "status": "running" if settings.GIGACHAT_CLIENT_ID else "config_required",
        "endpoints": {
            "auth": ["/auth/register", "/auth/login", "/auth/refresh", "/auth/me", "/auth/logout", "/auth/consent"],
            "chat": ["/chat/new", "/chat/list", "/chat/{chat_id}/send_stream", "/chat/feedback"],
            "admin": ["/admin/monitor-laws"],
            "court_filings": [
                "/court-filings/submissions",
                "/court-filings/submissions/{filing_id}",
                "/court-filings/submissions/{filing_id}/status",
            ],
            "notifications": ["/notifications", "/notifications/{notification_id}/read", "/api/ws/notifications?token=..."],
            "docs": "/docs",
            "health": "/health"
        },
        "features": {
            "gigachat": bool(settings.GIGACHAT_CLIENT_ID),
            "celery_monitoring": bool(settings.CELERY_BROKER_URL),
            "pgvector": getattr(settings, 'ENABLE_PGVECTOR', False),
            "law_monitoring": True
        }
    }

@app.get("/health", tags=["📊 Status"])
async def health():
    """Health check"""
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "environment": getattr(settings, 'ENVIRONMENT', 'dev'),
        "debug": settings.DEBUG,
        "timestamp": "2026-03-22"  # Обновлено
    }

@app.get("/config", tags=["📊 Status"])
async def config_info(request: Request):
    """Конфигурация (без DB)"""
    return {
        "app_name": settings.APP_NAME,
        "debug": settings.DEBUG,
        "environment": getattr(settings, 'ENVIRONMENT', 'dev'),
        "gigachat_ready": bool(settings.GIGACHAT_CLIENT_ID and settings.GIGACHAT_CLIENT_SECRET),
        "celery_ready": bool(settings.CELERY_BROKER_URL),
        "pgvector": getattr(settings, 'ENABLE_PGVECTOR', False),
        "docs": f"{request.url.path}../docs"
    }

@app.get("/status/law-monitoring", tags=["📊 Status"])
async def law_monitoring_status(db: AsyncSession = Depends(get_db)):
    """Статус мониторинга (CRUD пример!)"""
    try:
        from app.db.base_class import get_crud
        from app.models.law_changes import LawChange
        
        crud = get_crud(LawChange)
        count = await crud.count(db)
        
        return {
            "service": "law_monitoring",
            "status": "active",
            "total_changes": count,
            "celery_tasks": "http://localhost:5555"
        }
    except Exception as e:
        return {
            "service": "law_monitoring", 
            "status": "initializing", 
            "error": str(e)
        }

# ✅ Обработчики ошибок
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    logger.warning("404: path=%s", request.url.path)
    return JSONResponse(status_code=404, content={"error": "Endpoint не найден", "docs": "/docs"})


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.warning("HTTPException: status=%s path=%s detail=%s", exc.status_code, request.url.path, exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning("Validation error: path=%s errors=%s", request.url.path, exc.errors())
    return JSONResponse(
        status_code=422,
        content={"error": "Validation failed", "details": exc.errors()},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Остаточный обработчик (HTTPException обрабатывается отдельно, см. MRO Starlette)."""
    import traceback

    traceback.print_exc()
    logger.exception("Unhandled exception on path=%s", request.url.path)
    if settings.DEBUG:
        return JSONResponse(
            status_code=500,
            content={"detail": f"{type(exc).__name__}: {exc}"},
        )
    return JSONResponse(
        status_code=500,
        content={"error": "Внутренняя ошибка сервера", "contact": "admin@ai-jurist.ru"},
    )

# ✅ Uvicorn
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info"
    )
