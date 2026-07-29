"""
Historical Order Entry — request/response schemas.

Superadmin-only, backdated `ServiceOrder` creation (paper orders written
when Sonia was unavailable). This schema module is the WHITELIST for the
new `POST /superadmin/data/historical-orders` endpoint — no dict from this
flow ever reaches a generic update helper, same rule already established by
`OrderQuickFixUpdate` (`app/api/v1/superadmin_data.py`).

Two decided non-goals, both from the design's Architecture Decisions:
  - No cédula/identification field anywhere (Decision 6) — the system has
    never captured a real cédula, and this feature does not become the
    first half-built place that starts.
  - No date-range validation (see Request Contract note) — any past/future
    date, including before the vehicle's registration date, is legal.
    NARROWLY SUPERSEDED by `sdd/distributor-vehicle-delivery` PR2: for a
    vehicle that HAS a registered `delivery_date` (set via the future
    Distribuidor screen), `created_at` may not precede it — see
    `historical_order_service.create_historical_order`'s call to
    `ensure_order_date_after_delivery`. Vehicles without a `delivery_date`
    (every vehicle today) keep the original, unrestricted behaviour.

`tenant_id` is REQUIRED (Decision 11): a superadmin's own JWT carries
`tenant_id=None` (`app/api/deps.py`), and `ServiceOrder.tenant_id` is NOT
NULL — there is no implicit tenant to fall back to.
"""
from decimal import Decimal
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.order import ServiceStatus, ServiceType


class HistoricalOrderVehicleIn(BaseModel):
    """Vehicle fields a superadmin may supply inline. Only `plate` is
    required — everything else may come from the VIN lookup
    (`vin_master_service.query_vin`, called AS-IS by
    `vehicle_service.register_or_update_vehicle` in the next PR)."""
    plate: str = Field(..., min_length=1)
    vin: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    color: Optional[str] = None


class HistoricalOrderClientIn(BaseModel):
    """Client fields a superadmin may supply inline. NO identification/
    cédula field — deliberately dropped from scope (Decision 6)."""
    name: str = Field(..., min_length=1)
    phone: Optional[str] = None


class HistoricalOrderCreate(BaseModel):
    tenant_id: UUID
    vehicle: HistoricalOrderVehicleIn
    client: HistoricalOrderClientIn
    service_type: ServiceType
    status: ServiceStatus
    mileage_km: Decimal = Field(..., ge=0)
    created_at: datetime
    completed_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    customer_notes: Optional[str] = Field(None, max_length=1000)
    diagnosis: Optional[str] = Field(None, max_length=2000)
    general_observations: Optional[str] = None
    technician_id: Optional[UUID] = None
    acknowledge_duplicate: bool = False


class DuplicateMatch(BaseModel):
    """One row of the 409 `DUPLICATE_ORDER_WARNING` envelope — an existing
    order on the same plate/date the superadmin may be re-entering by
    mistake. Confirmed via `acknowledge_duplicate=True` on the re-POST."""
    order_id: UUID
    plate: str
    created_at: datetime
    status: ServiceStatus


class HistoricalOrderOut(BaseModel):
    id: UUID
    tenant_id: UUID
    vehicle_id: UUID
    client_id: UUID
    status: ServiceStatus
    service_type: ServiceType
    created_at: datetime
    completed_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
