import asyncio
from app.database import async_session_maker
from app.models.user import User, Role, UserStatus
from app.core.security import get_password_hash
from sqlalchemy.future import select

async def create_superadmin():
    async with async_session_maker() as session:
        telegram_id = "819921357"
        email = "admin@umcolombia.co"
        password = "umadmin2026"
        
        # Verificar si ya existe
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
        print(f"🔑 Password: {password}")
        print(f"🤖 Telegram ID: {telegram_id}")

if __name__ == "__main__":
    asyncio.run(create_superadmin())
