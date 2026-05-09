import asyncio
import os
import sys
from app.database import async_session_maker
from app.models.user import User, Role, UserStatus
from app.core.security import get_password_hash
from sqlalchemy.future import select

async def create_superadmin():
    telegram_id = os.getenv("ADMIN_TELEGRAM_ID")
    email = os.getenv("ADMIN_EMAIL")
    password = os.getenv("ADMIN_PASSWORD")

    if not telegram_id or not email or not password:
        print("❌ ERROR: Variables de entorno requeridas no configuradas.")
        print("   Ejecutar con: ADMIN_TELEGRAM_ID=xxx ADMIN_EMAIL=xxx ADMIN_PASSWORD=xxx python create_admin.py")
        sys.exit(1)

    async with async_session_maker() as session:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if user:
            print(f"Actualizando usuario existente con ID {telegram_id}...")
            user.role = Role.superadmin
            user.status = UserStatus.active
            user.email = email
            user.hashed_password = get_password_hash(password)
            user.name = "Administrador Principal"
        else:
            print(f"Creando nuevo superadmin con ID {telegram_id}...")
            user = User(
                name="Administrador Principal",
                telegram_id=telegram_id,
                email=email,
                hashed_password=get_password_hash(password),
                role=Role.superadmin,
                status=UserStatus.active
            )
            session.add(user)

        await session.commit()
        print(f"✅ SUPERADMIN creado/actualizado exitosamente.")
        print(f"📧 Email: {email}")
        print(f"🤖 Telegram ID: {telegram_id}")
        # No se imprime la contraseña en logs

if __name__ == "__main__":
    asyncio.run(create_superadmin())
