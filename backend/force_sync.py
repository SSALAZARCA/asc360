import asyncio
from app.database import engine, Base

async def init_db():
    async with engine.begin() as conn:
        print("Creando todas las tablas faltantes desde cero (Docker Asyncpg)...")
        await conn.run_sync(Base.metadata.create_all)
    print("Migración Asíncrona Finalizada Perfectamente.")

if __name__ == "__main__":
    asyncio.run(init_db())
