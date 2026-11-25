"""
Legal AI Service — Async SQLAlchemy Session
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import event
import os
import socket
from urllib.parse import urlsplit, urlunsplit


def _native_local_database_url(url: str) -> str:
    """Use the Docker database hostname when it resolves, otherwise fall back
    to the published local PostgreSQL port for a native (non-Docker) run.

    ``backend/.env`` intentionally contains the Compose hostname ``db``.  The
    local developer server is often started directly with uvicorn, where that
    name is not present in DNS even though PostgreSQL is published on
    127.0.0.1:5432.  Resolving before creating the engine keeps Docker
    untouched and prevents every authenticated endpoint from returning 500 in
    a native run.
    """
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        if host not in {"db", "postgres", "postgresql"}:
            return url
        # Docker's service name resolves inside Compose.  Do not rewrite it.
        try:
            socket.getaddrinfo(host, parsed.port or 5432, type=socket.SOCK_STREAM)
            return url
        except OSError:
            pass
        # Only use the fallback when the local published port is reachable;
        # otherwise preserve the original URL so the normal startup error is
        # visible instead of masking a genuinely stopped database.
        try:
            with socket.create_connection(("127.0.0.1", parsed.port or 5432), timeout=0.25):
                pass
        except OSError:
            return url
        userinfo = ""
        if parsed.username is not None:
            userinfo = parsed.username
            if parsed.password is not None:
                userinfo += f":{parsed.password}"
            userinfo += "@"
        netloc = f"{userinfo}127.0.0.1"
        if parsed.port:
            netloc += f":{parsed.port}"
        return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
    except Exception:
        return url

# ✅ БЕЗОПАСНЫЙ импорт config
try:
    from app.core.config import settings
    DATABASE_URL = settings.DATABASE_URL
    ENABLE_PGVECTOR = getattr(settings, 'ENABLE_PGVECTOR', False)
except ImportError:
    DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql+asyncpg://postgres:postgres@db:5432/legal_ai')
    ENABLE_PGVECTOR = False

# ✅ Async engine.  Keep the Compose URL in Docker, but make native uvicorn
# runs work when PostgreSQL is exposed on localhost and ``db`` is not DNS-
# resolvable.
DATABASE_URL = _native_local_database_url(DATABASE_URL)
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
        # Если расширение недоступно/нет прав, очищаем failed transaction state,
        # иначе последующие SQL-команды на этом соединении падают с
        # InFailedSQLTransactionError.
        try:
            dbapi_connection.rollback()
        except Exception:
            pass

# ✅ FastAPI dependency
# Коммит выполняется в CRUD/роутерах (await db.commit()), а не здесь — иначе двойной commit
# после успешного user.create() давал InvalidRequestError и ответ 500.
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
