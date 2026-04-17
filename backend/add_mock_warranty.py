import asyncio
import uuid
from app.database import async_session_maker
import sqlalchemy as sa
import json

async def main():
    async with async_session_maker() as db:
        # Obtenemos cualquier tenant existente (un centro)
        result = await db.execute(sa.text("SELECT id FROM tenants LIMIT 1"))
        tenant_id = result.scalar_one_or_none()
        
        if not tenant_id:
            print("No se encontro un tenant/centro en BD para asociar la orden.")
            return

        # Obtenemos un cliente de prueba
        result = await db.execute(sa.text("SELECT id FROM users LIMIT 1"))
        user_id = result.scalar_one_or_none()

        vehicle_id = str(uuid.uuid4())
        order_id = str(uuid.uuid4())
        reception_id = str(uuid.uuid4())
        history_id = str(uuid.uuid4())

        # 1. Crear vehiculo para la garantia
        await db.execute(sa.text("""
            INSERT INTO vehicles (id, tenant_id, plate, vin, brand, model, year, color, mileage)
            VALUES (:vid, :tid, 'WAR001', 'LVUM500XXX2026M01', 'UM', 'RENEGADE SPORT 200', 2026, 'Rojo', 1500)
        """), {"vid": vehicle_id, "tid": tenant_id})

        # 2. Crear orden de garantia en proceso
        await db.execute(sa.text("""
            INSERT INTO service_orders (id, tenant_id, vehicle_id, client_id, technician_id, status, service_type, created_at)
            VALUES (:oid, :tid, :vid, :uid, :uid, 'in_progress', 'warranty', now() - interval '3 days')
        """), {"oid": order_id, "tid": tenant_id, "vid": vehicle_id, "uid": user_id})

        # 3. Crear recepción detallada con los datos para Softway
        photos = json.dumps(["https://images.unsplash.com/photo-1558981403-c5f9899a28bc?q=80&w=400"])
        await db.execute(sa.text("""
            INSERT INTO service_order_receptions (id, order_id, mileage_km, gas_level, customer_notes, warranty_warnings, damage_photos_urls)
            VALUES (:rid, :oid, 1500, 'MEDIO', 'El modulo electronico se apaga repentinamente cuando la moto supera las 6000 RPM. El faro delantero se quemo sin razon aparente.', 'Instaló exploradoras no originales, pero el corto parece venir de fabrica.', :photos)
        """), {"rid": reception_id, "oid": order_id, "photos": photos})

        # 4. Crear historial
        await db.execute(sa.text("""
            INSERT INTO order_history (id, order_id, from_status, to_status, changed_by, duration_minutes, comments, changed_at)
            VALUES (:hid, :oid, 'received', 'in_progress', :uid, 2800, 'El cliente reporto riesgo de incendio electrico. Se ingreso urgente.', now() - interval '2 days')
        """), {"hid": history_id, "oid": order_id, "uid": user_id})

        await db.commit()
        print(f"✅ Orden ficticia de garantia (WAR001) creada con exito en BD.")

if __name__ == "__main__":
    asyncio.run(main())
