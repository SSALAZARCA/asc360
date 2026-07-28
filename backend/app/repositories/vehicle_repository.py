from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, true
from sqlalchemy.orm import selectinload
from app.models.order import ServiceOrder, ServiceStatus

from app.repositories.base_repository import BaseRepository
from app.models.vehicle import Vehicle
from app.schemas.vehicle import VehicleCreate, VehicleUpdate
from uuid import UUID

# ---------------------------------------------------------------------------
# Vehicle tenant claim (sdd/vehicle-tenant-checkin-release) -- module-level
# predicates, reused by every lookup site so the claim rule has exactly one
# definition. Vehicle V is held by tenant T iff there exists a ServiceOrder
# with vehicle_id=V, tenant_id=T, status NOT IN RELEASING_STATUSES.
#
# RELEASING_STATUSES IS DELIBERATELY A FOURTH, DIFFERENT CLOSED-SET.
# This codebase already has TWO other "order is closed" sets that must NOT
# be touched or unified with this one:
#   - `get_by_plate` below (display-only `active_order` flag):
#     CLOSED = {"completed", "delivered"}
#   - `app/api/v1/orders.py` (multiple display/exclude lists):
#     {"completed", "delivered", "cancelled"}
# The CLAIM set intentionally excludes `completed`: a `completed` order
# means the WORK is finished, but the bike is still PHYSICALLY in the shop
# until it is `delivered` -- so it must still hold the claim. If someone
# "helpfully" unifies this with either display set above, vehicles will be
# silently released (and claimable elsewhere) while still sitting on the
# shop floor. Do not touch the other two sets from this change.
RELEASING_STATUSES = (ServiceStatus.delivered, ServiceStatus.cancelled)


def claimed_by_other_tenant(tenant_id: UUID, *, exclude_order_id: Optional[UUID] = None):
    """Correlated EXISTS: the vehicle has an OPEN order owned by a DIFFERENT
    tenant. Correlates on `Vehicle.id` -- only valid inside a select whose
    FROM already includes `Vehicle` (SQLAlchemy auto-correlates it out of
    this subquery's own FROM in that case)."""
    stmt = select(ServiceOrder.id).where(
        ServiceOrder.vehicle_id == Vehicle.id,
        ServiceOrder.status.not_in(RELEASING_STATUSES),
        ServiceOrder.tenant_id != tenant_id,
    )
    if exclude_order_id is not None:
        stmt = stmt.where(ServiceOrder.id != exclude_order_id)
    return stmt.exists()


def visible_to_tenant(tenant_id: Optional[UUID]):
    """Lookup filter. `tenant_id=None` (superadmin) -> `true()` -- the exact
    sqlalchemy singleton, byte-identical to an unfiltered predicate, so
    superadmin's network-wide view is mechanically guaranteed unchanged.
    Otherwise: unclaimed OR claimed by me, expressed as NOT claimed-by-
    someone-else (one predicate, both cases)."""
    return true() if tenant_id is None else ~claimed_by_other_tenant(tenant_id)


@dataclass(frozen=True)
class VehicleClaim:
    """Who currently holds a vehicle -- for the 409 conflict body and the
    conflict notification. Not tenant-scoped: answers "who has it", not
    "can tenant T see it" (that's `visible_to_tenant`)."""

    tenant_id: UUID
    tenant_name: Optional[str]
    tenant_city: Optional[str]
    order_id: UUID
    status: str
    since: Optional[datetime]


async def get_open_claim(
    db: AsyncSession, vehicle_id: UUID, *, exclude_order_id: Optional[UUID] = None
) -> Optional["VehicleClaim"]:
    """Most recent OPEN order for the vehicle, joined to its Tenant. `None`
    when the vehicle is unclaimed."""
    from app.models.tenant import Tenant

    stmt = (
        select(ServiceOrder, Tenant)
        .join(Tenant, Tenant.id == ServiceOrder.tenant_id)
        .where(
            ServiceOrder.vehicle_id == vehicle_id,
            ServiceOrder.status.not_in(RELEASING_STATUSES),
        )
    )
    if exclude_order_id is not None:
        stmt = stmt.where(ServiceOrder.id != exclude_order_id)
    stmt = stmt.order_by(desc(ServiceOrder.created_at)).limit(1)

    result = await db.execute(stmt)
    row = result.first()
    if row is None:
        return None

    order, tenant = row
    return VehicleClaim(
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        tenant_city=tenant.ciudad,
        order_id=order.id,
        status=order.status.value,
        since=order.created_at,
    )


class VehicleRepository(BaseRepository[Vehicle, VehicleCreate, VehicleUpdate]):
    """Repositorio para la entidad Vehicle (Placas/Motos de Clientes)."""

    async def get_by_plate(self, db: AsyncSession, plate: str, tenant_id: Optional[UUID] = None) -> Optional[Vehicle]:
        """Obtener vehículo por placa. `tenant_id=None` busca en toda la red
        (Admin); de lo contrario, ve vehículos sin claim o reclamados por
        ese tenant (`visible_to_tenant`,
        sdd/vehicle-tenant-checkin-release PR2)."""
        from app.models.order import ServiceOrderReception
        from app.models.tenant import Tenant
        if isinstance(tenant_id, str):
            tenant_id = UUID(tenant_id)
        stmt = (
            select(Vehicle)
            .options(
                selectinload(Vehicle.service_orders).selectinload(ServiceOrder.client),
                selectinload(Vehicle.service_orders).selectinload(ServiceOrder.reception),
                selectinload(Vehicle.service_orders).selectinload(ServiceOrder.tenant),
            )
            .where(Vehicle.plate == plate)
            .where(visible_to_tenant(tenant_id))
        )
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
        elif vehicle:
            setattr(vehicle, 'latest_mileage', None)
            setattr(vehicle, 'active_order', None)
            setattr(vehicle, 'service_orders_summary', [])

        return vehicle

    async def get_by_vin(self, db: AsyncSession, vin: str, tenant_id: Optional[UUID] = None) -> Optional[Vehicle]:
        """Obtener vehículo por VIN físico. `tenant_id=None` busca en toda
        la red; de lo contrario, aplica `visible_to_tenant` (mismo
        criterio de claim que `get_by_plate`). Nota: sin llamadores reales
        verificados hoy -- reescrito por consistencia
        (sdd/vehicle-tenant-checkin-release PR2)."""
        if isinstance(tenant_id, str):
            tenant_id = UUID(tenant_id)
        result = await db.execute(
            select(Vehicle).where(
                Vehicle.vin == vin,
                visible_to_tenant(tenant_id),
            )
        )
        return result.scalars().first()

vehicle_repository = VehicleRepository(Vehicle)
