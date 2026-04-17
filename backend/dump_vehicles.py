
import asyncio
from sqlalchemy import select
from app.database import async_session_maker, AsyncSession
from app.models.vehicle import Vehicle

async def dump_vehicles():
    async with async_session_maker() as db:
        stmt = select(Vehicle)
        result = await db.execute(stmt)
        vehicles = result.scalars().all()
        for v in vehicles:
            print(f"ID: {v.id}, Plate: '{v.plate}', Tenant: {v.tenant_id}")

if __name__ == "__main__":
    asyncio.run(dump_vehicles())
