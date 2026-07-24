"""
Superadmin Data Editor — Vehículo + Orden quick-fix.

Two self-contained, whitelisted, superadmin-only endpoints that let a
superadmin correct bad intake data (vehicle identifiers, order dates,
mileage/service_type) without SQL access. Mirrors the `app/api/v1/settings.py`
pattern: an internal `APIRouter`, inline Pydantic bodies acting as the
whitelist (no dict is ever passed to a generic update helper), and a
per-route `current_user.is_superadmin` guard.

Phase 1: router registration + both request schemas + guarded route stubs.
Phase 2 (this batch): Vehicle quick-fix GET/PUT — whitelist diff per field,
one audit row per changed field, 409 on duplicate-plate conflict, no audit
row on a no-op submission. Order quick-fix (Phase 3: dates, Phase 4:
mileage/service_type + lifecycle sync, Phase 5: confirm-then-delete) still
returns 501 and lands in later apply batches.
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
from app.models.order import ServiceType
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

    changes: dict = {}
    for field_name, new_value in payload.model_dump().items():
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


@router.get("/orders")
async def search_orders(
    plate: Optional[str] = None,
    order_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Búsqueda de orden por placa/id. Implementación real: Fase 3."""
    _require_superadmin(current_user)
    raise HTTPException(status_code=501, detail="Not implemented yet")


@router.put("/orders/{order_id}")
async def update_order(
    order_id: uuid.UUID,
    payload: OrderQuickFixUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Corrección de fechas/kilometraje/tipo de servicio de orden.
    Implementación real: Fases 3-5 (fechas, sync de ciclo de vida,
    confirm-then-delete)."""
    _require_superadmin(current_user)
    raise HTTPException(status_code=501, detail="Not implemented yet")
