from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload
from app.models.order import ServiceOrder

from app.repositories.base_repository import BaseRepository
from app.models.vehicle import Vehicle
from app.schemas.vehicle import VehicleCreate, VehicleUpdate
from uuid import UUID

class VehicleRepository(BaseRepository[Vehicle, VehicleCreate, VehicleUpdate]):
    """Repositorio para la entidad Vehicle (Placas/Motos de Clientes)."""

    async def get_by_plate(self, db: AsyncSession, plate: str, tenant_id: UUID = None) -> Optional[Vehicle]:
        """Obtener vehículo por placa. Si tenant_id es None, busca en toda la red (Admin)."""
        from app.models.order import ServiceOrderReception
        from app.models.tenant import Tenant
        stmt = (
            select(Vehicle)
            .options(
                selectinload(Vehicle.service_orders).selectinload(ServiceOrder.client),
                selectinload(Vehicle.service_orders).selectinload(ServiceOrder.reception),
                selectinload(Vehicle.service_orders).selectinload(ServiceOrder.tenant),
            )
            .where(Vehicle.plate == plate)
        )
        if tenant_id:
            stmt = stmt.where(Vehicle.tenant_id == tenant_id)
        result = await db.execute(stmt)
        vehicle = result.scalars().first()

        if vehicle and vehicle.service_orders:
            sorted_orders = sorted(vehicle.service_orders, key=lambda o: o.created_at, reverse=True)
            latest_order = sorted_orders[0]

            # Inyectar último cliente
            if latest_order.client:
                setattr(vehicle, 'client', {'id': str(latest_order.client.id), 'name': latest_order.client.name, 'phone': latest_order.client.phone})
                setattr(vehicle, 'client_id', latest_order.client.id)

            # KM real: de la recepción más reciente que lo tenga
            latest_km = None
            for o in sorted_orders:
                if o.reception and o.reception.mileage_km:
                    latest_km = int(o.reception.mileage_km)
                    break
            if latest_km is not None:
                setattr(vehicle, 'latest_mileage', latest_km)

            # Orden activa (la más reciente que no esté cerrada)
            CLOSED = {"completed", "delivered"}
            active = next((o for o in sorted_orders if o.status.value not in CLOSED), None)
            if active:
                setattr(vehicle, 'active_order', {
                    "status": active.status.value,
                    "tenant_name": active.tenant.name if active.tenant else None,
                    "tenant_city": active.tenant.ciudad if active.tenant else None,
                    "created_at": active.created_at.isoformat() if active.created_at else None,
                })
            else:
                setattr(vehicle, 'active_order', None)

            # Historial de órdenes para el bot (máximo 5)
            setattr(vehicle, 'service_orders_summary', [
                {
                    "status": o.status.value,
                    "created_at": o.created_at.isoformat() if o.created_at else None,
                    "mileage_km": int(o.reception.mileage_km) if o.reception and o.reception.mileage_km else None,
                }
                for o in sorted_orders[:5]
            ])
        else:
            setattr(vehicle, 'latest_mileage', None)
            setattr(vehicle, 'active_order', None)
            setattr(vehicle, 'service_orders_summary', [])

        return vehicle

    async def get_by_vin(self, db: AsyncSession, vin: str, tenant_id: UUID) -> Optional[Vehicle]:
        """Obtener vehículo por VIN físico, aislado por tenant."""
        result = await db.execute(
            select(Vehicle).where(
                Vehicle.vin == vin,
                Vehicle.tenant_id == tenant_id
            )
        )
        return result.scalars().first()

vehicle_repository = VehicleRepository(Vehicle)
