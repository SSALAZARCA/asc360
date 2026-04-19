import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import sys
import os

# Añadir el raíz del proyecto al PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import async_session_maker
from app.models.user import User, Role, UserStatus
from app.core.security import get_password_hash

async def create_superadmin():
    async with async_session_maker() as session:
        # Verificar si ya existe
        stmt = select(User).where(User.email == "admin@umcolombia.co")
        res = await session.execute(stmt)
        existing_admin = res.scalar_one_or_none()

        if existing_admin:
            print("El superadmin ya existe. No se modifica.")
            return

        # Crear nuevo admin
        admin = User(
            name="Super Admin UM",
            email="admin@umcolombia.co",
            role=Role.superadmin,
            status=UserStatus.active,
            hashed_password=get_password_hash("admin123")
        )
        session.add(admin)
        await session.commit()
        print("Superadmin admin@umcolombia.co creado exitosamente con contraseña 'admin123'.")

if __name__ == "__main__":
    asyncio.run(create_superadmin())
