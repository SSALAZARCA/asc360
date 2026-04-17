import asyncio
from sqlalchemy.future import select
from app.database import async_session_maker
from app.models.tenant import Tenant
from app.models.vehicle import Vehicle
import httpx

async def main():
    # 1. Obtenemos un Tenant real y un Vehiculo real de la Base de datos
    async with async_session_maker() as session:
        result_tenant = await session.execute(select(Tenant.id).limit(1))
        tenant_id = result_tenant.scalar_one_or_none()
        
        result_vehicle = await session.execute(select(Vehicle.id).limit(1))
        vehicle_id = result_vehicle.scalar_one_or_none()

    if not tenant_id or not vehicle_id:
        print("ERROR: Corra el seed o agregue un Vehiculo a la DB primero.")
        return

    print(f"Usando TENANT: {tenant_id}")
    print(f"Usando VEHÍCULO: {vehicle_id}")

    # 2. Formulamos el JSON de la Petición
    payload = {
        "tenant_id": str(tenant_id),
        "vehicle_id": str(vehicle_id),
        "service_type": "regular",
        "reception": {
            "mileage_km": 15400,
            "gas_level": "Medio",
            "customer_notes": "Cambio de aceite y ajustar frenos.",
            "warranty_warnings": "⚠️ Cliente se retrasó 2000km para la revisión de Cunas.",
            "damage_photos_urls": ["http://minio/bucket/foto1.jpg"]
        }
    }

    # 3. Empujamos el Request directamente por Python (HTTpx)
    print("Enviando POST a http://localhost:8000/api/v1/orders/")
    
    async with httpx.AsyncClient() as client:
        response = await client.post("http://localhost:8000/api/v1/orders/", json=payload)
        
        print(f"Status Code: {response.status_code}")
        try:
            print("Response JSON:", response.json())
        except Exception:
            print("Response Text:", response.text)

if __name__ == "__main__":
    asyncio.run(main())
