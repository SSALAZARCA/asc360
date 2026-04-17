
import asyncio
from sqlalchemy import select
from app.database import async_session_maker
from app.models.vehicle import Vehicle
from app.models.user import User

async def debug_db():
    async with async_session_maker() as db:
        print("--- VEHICLES ---")
        v_stmt = select(Vehicle)
        v_res = await db.execute(v_stmt)
        for v in v_res.scalars().all():
            print(f"Plate: '{v.plate}', Tenant: {v.tenant_id}")
            
        print("\n--- USERS ---")
        u_stmt = select(User)
        u_res = await db.execute(u_stmt)
        for u in u_res.scalars().all():
            print(f"Name: {u.name}, Role: {u.role}, TelegramID: {u.telegram_id}, Tenant: {u.tenant_id}")

if __name__ == "__main__":
    asyncio.run(debug_db())
