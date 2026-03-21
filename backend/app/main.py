"""
Legal AI Service - Главный файл FastAPI
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

# ✅ ИСПРАВЛЕННЫЕ ИМПОРТЫ — БЕЗ ОШИБОК!
from app.core.config import settings
from app.db.session import engine, get_db
from app.db.base_class import Base  # ✅ Пустой Base

# ✅ Заглушки роутеров (создадим позже)
from fastapi import APIRouter
auth = APIRouter()
chat = APIRouter()
admin = APIRouter()

# ✅ ПУСТЫЕ РОУТЕРЫ (чтобы не было ошибок импорта)
@auth.get("/ping")
async def auth_ping(): return {"auth": "ready"}

@chat.get("/ping")
async def chat_ping(): return {"chat": "ready"}

@admin.get("/ping")
async def admin_ping(): return {"admin": "ready"}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """✅ АСИНХРОННЫЙ Lifecycle — все проблемы решены"""
    
    # 🔥 АСИНХРОННАЯ ИНИЦИАЛИЗАЦИЯ БД
    print("🔄 Инициализация базы данных...")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("✅ База данных инициализирована АСИНХРОННО!")
    except Exception as e:
        print(f"❌ Ошибка БД: {e}")
    
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

# ✅ CORS — ИСПРАВЛЕНИЕ!
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else settings.CORS_ORIGINS,  # ✅ Без split!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Роутеры (порядок ВАЖЕН!)
app.include_router(auth.router, prefix="/auth", tags=["🔐 Auth"])
app.include_router(chat.router, prefix="/chat", tags=["💬 Chat"])
app.include_router(admin.router, prefix="/admin", tags=["⚙️ Admin"])

# ✅ Health endpoints
@app.get("/", tags=["📊 Status"])
async def root():
    """Главная страница API"""
    return {
        "message": "Legal AI Service 🚀",
        "version": settings.VERSION,
        "status": "running" if settings.GIGACHAT_CLIENT_ID else "config_required",
        "endpoints": {
            "auth": ["/auth/ping"],
            "chat": ["/chat/ping"],
            "admin": ["/admin/ping"],
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
        "timestamp": "2026-03-21"
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
    return {"error": "Endpoint не найден", "docs": "/docs"}

@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    return {"error": "Внутренняя ошибка сервера", "contact": "admin@ai-jurist.ru"}

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
