import os
import asyncio
from sqlalchemy.future import select
from app.database import async_session_maker
from app.models.tenant import Tenant, TenantType
from app.models.user import User, Role
from app.models.vehicle import Vehicle

async def insert_test_data():
    async with async_session_maker() as session:
        # 1. Crear Taller (Tenant)
        tenant = Tenant(
            id="9c2c248e-fe13-4138-aecd-edfa5e37a537",
            name="Taller Prueba UM", 
            subdomain="test-workshop",
            tenant_type=TenantType.service_center
        )
        session.add(tenant)
        await session.flush()
        
        # 2. Crear Dueño (User Client)
        client = User(
            name="Juan Pérez",
            telegram_id="999999999", 
            role=Role.client,
            tenant_id=tenant.id
        )
        session.add(client)
        await session.flush()
        
        # 3. Crear Motocicleta
        vehicle = Vehicle(
            vin="12345678901234567",
            plate="ABC12D",
            brand="UM",
            model="Renegade Classic 200",
            tenant_id=tenant.id
        )
        session.add(vehicle)
        
        await session.commit()
        print("SEMILLA DE DATOS COMPLETADA EXITOSAMENTE.")

if __name__ == "__main__":
    asyncio.run(insert_test_data())
