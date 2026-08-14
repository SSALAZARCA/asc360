from pydantic import BaseModel, ConfigDict, EmailStr
from typing import Any, List, Optional
from uuid import UUID

class VehicleBase(BaseModel):
    plate: str
    vin: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    color: Optional[str] = None
    mileage: Optional[int] = None

class VehicleCreate(VehicleBase):
    """sdd/vehicle-tenant-checkin-release PR2: `tenant_id` REMOVED (not
    made Optional). A vehicle's tenant is now a derived, temporary claim
    computed from open ServiceOrder rows -- never a value the client can
    set on the vehicle record itself. Pydantic ignores unknown input keys
    by default, so a legacy caller still POSTing `tenant_id` is tolerated,
    not 422'd."""
    pass

class VehicleUpdate(VehicleBase):
    plate: Optional[str] = None


class VehicleClientOut(BaseModel):
    """sdd/distributor-vehicle-delivery PR5 (design-dual-channel ADR 19):
    shared shape for the linked client's contact data, returned
    IDENTICALLY by both reception surfaces -- the Mini App's hand-built
    dict (`mini_app_get_vehicle`, ADR 14) and the bot's `VehicleOut`
    auto-conversion (`GET /vehicles/{plate}`, this model)."""
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ClientEditIn(BaseModel):
    """sdd/distributor-vehicle-delivery PR5 (design-dual-channel ADR 20):
    input for `PATCH /vehicles/{plate}/client`. All fields optional --
    the endpoint applies only what's actually submitted
    (`exclude_unset`).

    sdd/reception-email-notification (ADR 7): `email` is `EmailStr` so a
    malformed address is rejected at capture time (BR3), not silently
    stored and only discovered when the reception send fails."""
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None


class VehicleOut(VehicleBase):
    id: UUID
    # sdd/vehicle-tenant-checkin-release PR2: RENAMED from `tenant_id:
    # UUID` (not merely made Optional). Keeping the name `tenant_id` would
    # let consumers keep reading it as permanent ownership; the rename
    # makes every consumer fail loudly instead of silently reading a
    # stale/missing value (Decision 2's principle applied to the wire
    # contract).
    claimed_by_tenant_id: Optional[UUID] = None
    claimed_by_tenant_name: Optional[str] = None
    # sdd/distributor-vehicle-delivery PR5 (ADR 19): was `Optional[Any] =
    # None` -- always `None` since `Vehicle` had no client relationship
    # until PR1 added `client_id`/`client`. Now a real nested model so
    # `from_attributes` conversion actually surfaces the linked client.
    client: Optional[VehicleClientOut] = None
    client_id: Optional[UUID] = None
    latest_mileage: Optional[int] = None
    active_order: Optional[Any] = None
    service_orders_summary: Optional[List[Any]] = None

    model_config = ConfigDict(from_attributes=True)
