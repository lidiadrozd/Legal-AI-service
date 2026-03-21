"""
Legal AI Service — Async SQLAlchemy Session
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import event, text
import os

# ✅ БЕЗОПАСНЫЙ импорт config
try:
    from app.core.config import settings
    DATABASE_URL = settings.DATABASE_URL
    ENABLE_PGVECTOR = getattr(settings, 'ENABLE_PGVECTOR', False)
except ImportError:
    DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql+asyncpg://postgres:postgres@db:5432/legal_ai')
    ENABLE_PGVECTOR = False

# ✅ Async engine
engine = create_async_engine(DATABASE_URL, echo=False)

AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# ✅ pgvector (опционально)
@event.listens_for(engine, "connect")
async def on_connect(dbapi_connection, connection_record):
    if ENABLE_PGVECTOR:
        try:
            await dbapi_connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        except:
            pass  # Игнорируем ошибки

# ✅ FastAPI dependency
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
