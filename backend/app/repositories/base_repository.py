from typing import Generic, TypeVar, Type, Optional, List, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from pydantic import BaseModel

ModelType = TypeVar("ModelType")
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)

class BaseRepository(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    """Repository Base para operaciones CRUD genéricas, según el patrón del skill fastapi-templates."""

    def __init__(self, model: Type[ModelType]):
        self.model = model

    async def get(self, db: AsyncSession, id: Any) -> Optional[ModelType]:
        """Obtener un registro por ID."""
        result = await db.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalars().first()

    async def get_multi(
        self,
        db: AsyncSession,
        skip: int = 0,
        limit: int = 100
    ) -> List[ModelType]:
        """Obtener múltiples registros con paginación básica."""
        result = await db.execute(
            select(self.model).offset(skip).limit(limit)
        )
        return result.scalars().all()

    async def create(
        self,
        db: AsyncSession,
        obj_in: CreateSchemaType
    ) -> ModelType:
        """Crear un nuevo registro."""
        # obj_in dict() a model attribute args
        obj_in_data = obj_in.model_dump()
        db_obj = self.model(**obj_in_data)
        db.add(db_obj)
        await db.flush()
        await db.refresh(db_obj)
        return db_obj

    async def update(
        self,
        db: AsyncSession,
        db_obj: ModelType,
        obj_in: UpdateSchemaType | dict
    ) -> ModelType:
        """Actualiza un registro (db_obj) con data (obj_in)."""
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.model_dump(exclude_unset=True)
            
        for field, value in update_data.items():
            setattr(db_obj, field, value)
            
        await db.flush()
        await db.refresh(db_obj)
        return db_obj

    async def delete(self, db: AsyncSession, id: Any) -> bool:
        """Eliminar registro por ID."""
        obj = await self.get(db, id)
        if obj:
            await db.delete(obj)
            await db.flush()
            return True
        return False
