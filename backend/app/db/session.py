
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import event
from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL, 
    echo=settings.DEBUG,
    future=True
)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

@event.listens_for(engine, "connect")
async def on_connect(dbapi_connection, connection_record):
    if settings.ENABLE_PGVECTOR:
        await dbapi_connection.execute("CREATE EXTENSION IF NOT EXISTS vector")

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
