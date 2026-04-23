# backend/app/crud/user.py
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base_class import CRUDBase
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
from app.core.security import get_password_hash, verify_password


class CRUDUser(CRUDBase[User, UserCreate, UserUpdate]):
    async def get_by_email(self, db: AsyncSession, *, email: str) -> Optional[User]:
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def create(self, db: AsyncSession, *, obj_in: UserCreate) -> User:
        db_obj = User(
            email=obj_in.email,
            full_name=obj_in.full_name,
            hashed_password=get_password_hash(obj_in.password),
        )
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def authenticate(
        self, db: AsyncSession, *, email: str, password: str
    ) -> Optional[User]:
        user_obj = await self.get_by_email(db, email=email)
        if not user_obj:
            return None
        if not verify_password(password, user_obj.hashed_password):
            return None
        return user_obj

    def is_active(self, user: User) -> bool:
        return bool(user.is_active)


user = CRUDUser(User)
