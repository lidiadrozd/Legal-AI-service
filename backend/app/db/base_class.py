"""
Legal AI Service — Async CRUD Base
"""
from typing import Any, Generic, List, Optional, TypeVar
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import select, func

# ✅ TypeVar ДО определения Base (без bound пока)
ModelType = TypeVar("ModelType")
CreateSchemaType = TypeVar("CreateSchemaType", bound=Any)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=Any)

# ✅ ЧИСТЫЙ Base — БЕЗ импортов моделей!
class Base(DeclarativeBase):
    """Базовый класс для моделей — НЕ импортируем ничего!"""
    pass

# ✅ TypeVar теперь с bound Base
ModelType = TypeVar("ModelType", bound=Base)

class CRUDBase(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    """✅ АСИНХРОННЫЙ CRUD репозиторий"""
    
    def __init__(self, model: type[ModelType]):
        self.model = model

    async def get(self, db: AsyncSession, id: Any) -> Optional[ModelType]:
        """Получить объект по ID"""
        if not hasattr(self.model, 'id'):
            return None
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
        # ✅ Безопасный model_dump (Pydantic v1/v2)
        if hasattr(obj_in, 'model_dump'):
            data = obj_in.model_dump()
        else:
            data = obj_in.dict()
            
        db_obj = self.model(**data)
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
        # ✅ Безопасный model_dump
        if hasattr(obj_in, 'model_dump'):
            update_data = obj_in.model_dump(exclude_unset=True)
        else:
            update_data = obj_in.dict(exclude_unset=True)
            
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
    ) -> Optional[ModelType]:
        """Удалить объект"""
        obj = await self.get(db, id=id)
        if obj:
            await db.delete(obj)
            await db.commit()
            return obj
        return None

    async def count(self, db: AsyncSession) -> int:
        """Подсчет объектов"""
        result = await db.execute(select(func.count()).select_from(self.model))
        return result.scalar() or 0

# ✅ УНИВЕРСАЛЬНЫЕ CRUD классы (создаются динамически)
class CRUDLawDocument(CRUDBase["LawDocument", Any, Any]):
    pass

class CRUDLawChange(CRUDBase["LawChange", Any, Any]):
    pass

class CRUDLawNotification(CRUDBase["LawNotification", Any, Any]):
    pass

# ✅ ФАБРИКА CRUD (рекомендуемый способ использования)
def get_crud(model: type[ModelType]) -> CRUDBase[ModelType, Any, Any]:
    """Создает CRUD для любой модели динамически"""
    class DynamicCRUD(CRUDBase[model, Any, Any]):
        pass
    return DynamicCRUD(model)

# ✅ Экспорт — БЕЗ импортов моделей!
__all__ = [
    "Base", "CRUDBase", "get_crud",
    "CRUDLawDocument", "CRUDLawChange", "CRUDLawNotification"
]
