"""
Legal AI Service — Async SQLAlchemy Session
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import event
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

# ✅ pgvector (опционально): слушатель только на sync_engine (AsyncEngine не поддерживает connect)
@event.listens_for(engine.sync_engine, "connect")
def on_connect(dbapi_connection, connection_record):
    if not ENABLE_PGVECTOR:
        return
    try:
        cur = dbapi_connection.cursor()
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cur.close()
    except Exception:
        pass

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
