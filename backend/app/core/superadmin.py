from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import get_password_hash
from app.models.user import User


async def ensure_superadmin_exists(db: AsyncSession) -> bool:
    """
    Creates configured superadmin if absent.
    Returns True when a new superadmin is created.
    """
    if not settings.SUPERADMIN_EMAIL or not settings.SUPERADMIN_PASSWORD:
        return False

    result = await db.execute(select(User).where(User.email == settings.SUPERADMIN_EMAIL))
    existing = result.scalar_one_or_none()
    if existing is not None:
        return False

    superadmin = User(
        email=settings.SUPERADMIN_EMAIL,
        full_name=settings.SUPERADMIN_FULL_NAME,
        hashed_password=get_password_hash(settings.SUPERADMIN_PASSWORD),
        is_active=True,
        is_superuser=True,
        consent_given=True,
    )
    db.add(superadmin)
    await db.commit()
    return True
