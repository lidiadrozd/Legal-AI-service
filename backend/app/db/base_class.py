
from typing import Any, Dict, Generic, List, Optional, TypeVar, AsyncIterator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase  # ✅ SQLAlchemy 2.0!
from sqlalchemy import select
from app.models.law_changes import LawDocument, LawChange, LawNotification 
from app.models.user import User  # Если есть

# ✅ Современный async TypeVar
ModelType = TypeVar("ModelType", bound=Base)
CreateSchemaType = TypeVar("CreateSchemaType", bound=Any)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=Any)

# ✅ Современный Base для SQLAlchemy 2.0 + async
class Base(DeclarativeBase):
    """Базовый класс для всех моделей"""
    pass

class CRUDBase(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    """✅ АСИНХРОННЫЙ CRUD репозиторий"""
    
    def __init__(self, model: type[ModelType]):
        self.model = model

    async def get(self, db: AsyncSession, id: Any) -> Optional[ModelType]:
        """Получить объект по ID"""
        result = await db.execute(select(self.model).where(self.model.id == id))
        return result.scalar_one_or_none()

    async def get_multi(
        self, db: AsyncSession, skip: int = 0, limit: int = 100
    ) -> List[ModelType]:
        """Получить список с пагинацией"""
        result = await db.execute(
            select(self.model).offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    async def create(
        self, 
        db: AsyncSession, 
        *, 
        obj_in: CreateSchemaType
    ) -> ModelType:
        """Создать объект"""
        db_obj = self.model(**obj_in.model_dump())  # ✅ Pydantic v2
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def update(
        self, 
        db: AsyncSession, 
        *, 
        db_obj: ModelType, 
        obj_in: UpdateSchemaType
    ) -> ModelType:
        """Обновить объект"""
        update_data = obj_in.model_dump(exclude_unset=True)  # ✅ Только измененные
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def remove(
        self, 
        db: AsyncSession, 
        *, 
        id: int
    ) -> ModelType:
        """Удалить объект"""
        obj = await self.get(db, id=id)
        if obj:
            await db.delete(obj)
            await db.commit()
        return obj

    async def count(self, db: AsyncSession) -> int:
        """Подсчет объектов"""
        from sqlalchemy import func
        result = await db.execute(select(func.count()).select_from(self.model))
        return result.scalar()

# ✅ Готовые CRUD классы для моделей
class LawDocumentsCRUD(CRUDBase[LawDocument, Any, Any]):
    pass

class LawChangesCRUD(CRUDBase[LawChange, Any, Any]):
    pass

class LawNotificationsCRUD(CRUDBase[LawNotification, Any, Any]):
    pass

# ✅ Экспорт для использования
__all__ = [
    "Base", "CRUDBase",
    "LawDocumentsCRUD", "LawChangesCRUD", "LawNotificationsCRUD"
]
