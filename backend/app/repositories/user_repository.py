from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.repositories.base_repository import BaseRepository
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate

class UserRepository(BaseRepository[User, UserCreate, UserUpdate]):
    """Repositorio específico para la entidad User."""

    async def get_by_telegram_id(self, db: AsyncSession, telegram_id: str) -> Optional[User]:
        """Obtener usuario por su ID de Telegram."""
        result = await db.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalars().first()

user_repository = UserRepository(User)
