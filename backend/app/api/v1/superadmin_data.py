"""
Superadmin Data Editor — Vehículo + Orden quick-fix.

Two self-contained, whitelisted, superadmin-only endpoints that let a
superadmin correct bad intake data (vehicle identifiers, order dates,
mileage/service_type) without SQL access. Mirrors the `app/api/v1/settings.py`
pattern: an internal `APIRouter`, inline Pydantic bodies acting as the
whitelist (no dict is ever passed to a generic update helper), and a
per-route `current_user.is_superadmin` guard.

Phase 1 (this file, first cut): router registration + both request schemas +
guarded route stubs. The actual search/update logic (Phase 2: Vehicle,
Phase 3: Order dates, Phase 4: mileage/service_type + lifecycle sync,
Phase 5: confirm-then-delete) lands in later apply batches — until then the
stubs return 501 for a superadmin caller so the route shape is stable and
frontend/integration work can start against it.
"""
from decimal import Decimal
from datetime import datetime
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.database import get_db
from app.api.deps import get_current_user, CurrentUser
from app.models.order import ServiceType

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


@router.get("/vehicles")
async def search_vehicles(
    plate: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Búsqueda de vehículo por placa. Implementación real: Fase 2."""
    _require_superadmin(current_user)
    raise HTTPException(status_code=501, detail="Not implemented yet")


@router.put("/vehicles/{vehicle_id}")
async def update_vehicle(
    vehicle_id: uuid.UUID,
    payload: VehicleQuickFixUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Corrección de datos de vehículo. Implementación real: Fase 2."""
    _require_superadmin(current_user)
    raise HTTPException(status_code=501, detail="Not implemented yet")


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
