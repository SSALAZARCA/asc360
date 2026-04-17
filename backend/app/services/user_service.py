from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.user_repository import user_repository
from app.schemas.user import UserCreate, UserUpdate
from app.models.user import User
# from app.core.security import get_password_hash # Por si se requiere en un futuro para dashboard web

class UserService:
    """Capa de lógica de negocio o servicios para Usuarios."""

    def __init__(self):
        self.repository = user_repository

    async def register_telegram_user(
        self,
        db: AsyncSession,
        user_in: UserCreate
    ) -> User:
        """Registrar un usuario que ingresó por Telegram."""
        
        # Validar si ya existe
        if user_in.telegram_id:
            existing = await self.repository.get_by_telegram_id(db, user_in.telegram_id)
            if existing:
                raise ValueError("El ID de Telegram ya está registrado en el sistema.")

        # Lógica de creación (password hashing iría aquí de ser necesario)
        user = await self.repository.create(db, user_in)
        return user

    async def get_user_by_telegram(
        self,
        db: AsyncSession,
        telegram_id: str
    ) -> Optional[User]:
        """Verificar ingreso por Telegram."""
        user = await self.repository.get_by_telegram_id(db, telegram_id)
        if not user:
            return None
        return user

user_service = UserService()
