import asyncio
import uuid
import json
from datetime import datetime
import sqlalchemy as sa
from app.database import async_session_maker
from app.services.pdf_service import generate_and_upload_reception_pdf

async def main():
    async with async_session_maker() as db:
        # Obtenemos la orden ficticia creada
        result = await db.execute(sa.text("SELECT id FROM service_orders WHERE created_at < now() ORDER BY created_at DESC LIMIT 1"))
        order_id = result.scalar_one_or_none()
        
        if not order_id:
            print("No se encontró la orden.")
            return

        order_data = {
            "order_id": str(order_id),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "center": "Centro Principal UM"
        }
        reception_data = {
            "mileage": 1500,
            "gas_level": "MEDIO",
            "customer_notes": "El modulo electronico se apaga repentinamente cuando la moto supera las 6000 RPM. Falla eléctrica general."
        }
        vehicle_data = {
            "brand": "UM",
            "model": "RENEGADE SPORT 200",
            "vin": "LVUM500XXX2026M01",
            "plate": "WAR001"
        }
        client_data = {
            "full_name": "Propietario Demo",
            "identification": "12345678"
        }

        print("Generando PDF y subiendolo a MinIO...")
        pdf_url = await generate_and_upload_reception_pdf(order_data, reception_data, vehicle_data, client_data)
        print(f"PDF Url Generada: {pdf_url}")

        await db.execute(sa.text("""
            UPDATE service_order_receptions 
            SET reception_pdf_url = :url 
            WHERE order_id = :oid
        """), {"url": pdf_url, "oid": order_id})
        
        await db.commit()
        print("✅ URL Inyectada en la BD. El PDF ya está disponible para descargar/ver.")

if __name__ == "__main__":
    asyncio.run(main())
