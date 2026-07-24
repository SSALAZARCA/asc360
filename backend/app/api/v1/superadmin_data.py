"""
Superadmin Data Editor — Vehículo + Orden quick-fix.

Two self-contained, whitelisted, superadmin-only endpoints that let a
superadmin correct bad intake data (vehicle identifiers, order dates,
mileage/service_type) without SQL access. Mirrors the `app/api/v1/settings.py`
pattern: an internal `APIRouter`, inline Pydantic bodies acting as the
whitelist (no dict is ever passed to a generic update helper), and a
per-route `current_user.is_superadmin` guard.

Phase 1: router registration + both request schemas + guarded route stubs.
Phase 2: Vehicle quick-fix GET/PUT — whitelist diff per field, one audit
row per changed field, 409 on duplicate-plate conflict, no audit row on a
no-op submission.
Phase 3 (this batch): Order quick-fix — dates only (`created_at`,
`delivered_at`). Same whitelist-diff-audit pattern as Vehicle, plus an
unconditional 422 block when the resulting `delivered_at` would precede
the resulting `created_at` — no exceptions, per the spec's
"Delivered-Before-Created Is Blocked Unconditionally" requirement.
`mileage_km`/`service_type` and the confirm-then-delete lifecycle sync
(Phase 4/Phase 5) are still no-ops on this route and land in later apply
batches.
"""
from decimal import Decimal
from datetime import datetime
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel, Field

from app.database import get_db
from app.api.deps import get_current_user, CurrentUser
from app.models.order import ServiceOrder, ServiceType
from app.models.vehicle import Vehicle
from app.services.imports_service import _log_audit

router = APIRouter(prefix="/superadmin/data", tags=["superadmin_data"])


class VehicleQuickFixUpdate(BaseModel):
    """Whitelisted vehicle fields a superadmin may correct.
    `plate`, `brand`, `model` are NOT NULL in `vehicles` — required here too."""
    plate: str
    brand: str
    model: str
    vin: Optional[str] = None
    color: Optional[str] = None
    year: Optional[int] = None
    mileage: Optional[int] = Field(None, ge=0)


class OrderQuickFixUpdate(BaseModel):
    """Whitelisted order fields a superadmin may correct.
    `mileage_km` lives on `ServiceOrderReception`, not `ServiceOrder`.
    `confirm_delete_event` only acknowledges the lifecycle-event deletion
    described in the design's confirm-then-delete flow — it never changes
    a field by itself."""
    created_at: datetime
    delivered_at: Optional[datetime] = None
    mileage_km: Optional[Decimal] = Field(None, ge=0)
    service_type: Optional[ServiceType] = None
    confirm_delete_event: bool = False


def _require_superadmin(current_user: CurrentUser) -> None:
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo superadmin")


def _serialize_vehicle(vehicle: Vehicle) -> dict:
    return {
        "id": str(vehicle.id),
        "plate": vehicle.plate,
        "vin": vehicle.vin,
        "brand": vehicle.brand,
        "model": vehicle.model,
        "color": vehicle.color,
        "year": vehicle.year,
        "mileage": vehicle.mileage,
    }


@router.get("/vehicles")
async def search_vehicles(
    plate: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Búsqueda de vehículo por placa (global, sin filtro de tenant —
    superadmin opera en toda la red)."""
    _require_superadmin(current_user)
    clean_plate = "".join(str(plate).split()).upper() if plate else None
    vehicle = None
    if clean_plate:
        stmt = select(Vehicle).where(Vehicle.plate == clean_plate)
        vehicle = (await db.execute(stmt)).scalars().first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")
    return _serialize_vehicle(vehicle)


@router.put("/vehicles/{vehicle_id}")
async def update_vehicle(
    vehicle_id: uuid.UUID,
    payload: VehicleQuickFixUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Corrección de datos de vehículo: diff por campo contra la base
    (el schema `VehicleQuickFixUpdate` YA es la whitelist — cualquier otro
    campo enviado se ignora), una fila de auditoría por campo cambiado, sin
    fila de auditoría si la petición es un no-op, y 409 si la placa nueva
    ya está en uso por otro vehículo."""
    _require_superadmin(current_user)
    vehicle = await db.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")

    # `exclude_unset=True` keeps fields the request body never mentioned out
    # of the dict entirely -- omitting an optional field must leave the DB
    # value untouched, while explicitly sending it as `null` is the one
    # legitimate way to clear it. Required fields (`plate`/`brand`/`model`)
    # have no default, so they are always present here regardless.
    changes: dict = {}
    for field_name, new_value in payload.model_dump(exclude_unset=True).items():
        old_value = getattr(vehicle, field_name)
        if str(old_value) != str(new_value):
            changes[field_name] = {"old": old_value, "new": new_value}
            setattr(vehicle, field_name, new_value)

    for field_name, change in changes.items():
        _log_audit(
            db, current_user, "SUPERADMIN_DATA_FIX", "Vehicle", str(vehicle.id),
            {field_name: change},
        )

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="La placa ya está registrada en otro vehículo",
        )

    await db.refresh(vehicle)
    return _serialize_vehicle(vehicle)


def _serialize_order(order: ServiceOrder) -> dict:
    return {
        "id": str(order.id),
        "plate": order.plate,
        "status": order.status.value if order.status else None,
        "service_type": order.service_type.value if order.service_type else None,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
    }


@router.get("/orders")
async def search_orders(
    plate: Optional[str] = None,
    order_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Búsqueda de orden por id (prioridad) o por placa (más reciente,
    global — sin filtro de tenant ni de estado, ya que un superadmin debe
    poder corregir órdenes históricas en cualquier estado)."""
    _require_superadmin(current_user)
    order = None
    if order_id:
        order = await db.get(ServiceOrder, order_id)
    elif plate:
        clean_plate = "".join(str(plate).split()).upper()
        stmt = (
            select(ServiceOrder)
            .join(Vehicle, ServiceOrder.vehicle_id == Vehicle.id)
            .where(Vehicle.plate == clean_plate)
            .order_by(ServiceOrder.created_at.desc())
            .limit(1)
        )
        order = (await db.execute(stmt)).scalars().first()
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    return _serialize_order(order)


# Fields corrected by this route today (Phase 3). `mileage_km`/`service_type`
# are already part of `OrderQuickFixUpdate` (Phase 1) but are intentionally
# NOT diffed/applied here — they map to `ServiceOrderReception`/lifecycle
# events and land in Phase 4/Phase 5.
_ORDER_DATE_FIELDS = ("created_at", "delivered_at")


@router.put("/orders/{order_id}")
async def update_order(
    order_id: uuid.UUID,
    payload: OrderQuickFixUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Corrección de fechas de orden (`created_at`/`delivered_at`): diff
    por campo contra la base, una fila de auditoría por campo cambiado,
    sin fila de auditoría si la petición es un no-op, y bloqueo
    incondicional (422) si la fecha de entrega resultante quedara antes
    que la fecha de creación resultante — sin excepciones.
    `mileage_km`/`service_type` y el sync de ciclo de vida se implementan
    en Fases 4-5."""
    _require_superadmin(current_user)
    order = await db.get(ServiceOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")

    # `exclude_unset=True` distinguishes "key absent from the request body"
    # from "key explicitly sent as null". A field the caller never mentioned
    # must not be diffed/applied at all -- the DB value is the effective
    # value for that field. `created_at` is required (no default) so it is
    # always present here; `delivered_at` may legitimately be absent.
    provided = payload.model_dump(exclude_unset=True)

    effective_created_at = provided.get("created_at", order.created_at)
    effective_delivered_at = (
        provided["delivered_at"] if "delivered_at" in provided else order.delivered_at
    )
    if effective_delivered_at is not None and effective_delivered_at < effective_created_at:
        raise HTTPException(
            status_code=422,
            detail="La fecha de entrega no puede ser anterior a la fecha de creación",
        )

    changes: dict = {}
    for field_name in _ORDER_DATE_FIELDS:
        if field_name not in provided:
            continue
        new_value = provided[field_name]
        old_value = getattr(order, field_name)
        if str(old_value) != str(new_value):
            changes[field_name] = {"old": old_value, "new": new_value}
            setattr(order, field_name, new_value)

    for field_name, change in changes.items():
        _log_audit(
            db, current_user, "SUPERADMIN_DATA_FIX", "ServiceOrder", str(order.id),
            {field_name: change},
        )

    await db.commit()
    await db.refresh(order)
    return _serialize_order(order)
