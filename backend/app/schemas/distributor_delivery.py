"""
Distributor Vehicle Delivery — request/response schemas.

`parts_dealer` (Distribuidor) or superadmin registration of a new
motorcycle sale/delivery: a client `User` and a `Vehicle` created (or
reused) in one transaction, with an authoritative warranty-start date
(`Vehicle.delivery_date`) and an optional (role-conditional) signed
delivery-act photo.

This schema module is the WHITELIST for the new
`POST /distributor/deliveries` endpoint — no dict from this flow ever
reaches a generic update helper, same rule already established by
`HistoricalOrderCreate` (`app/schemas/historical_order.py`).

Design Decision 4 (`sdd/distributor-vehicle-delivery`): `delivery_date`/
`engine_number`/`delivery_act_url` are deliberately NOT added to
`VehicleCreate`/`VehicleBase` — the delivery service (PR4) calls
`register_or_update_vehicle(db, vehicle_in)` AS-IS, then sets those 3
attributes directly on the returned ORM instance, inside the same
transaction, before `commit()`. Adding them to `VehicleCreate` would let a
client-controlled value hard-block reception for that bike (the
mass-assignment class flagged in `vehicle-tenant-checkin-release`).
`DeliveryVehicleIn` below is that intentionally narrower, delivery-scoped
whitelist — not a superset of `VehicleCreate`.
"""
from datetime import date
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DeliveryClientIn(BaseModel):
    """Client fields a Distribuidor/superadmin may supply inline.
    `identification` (cédula) is the lookup-or-create key (Design Decision
    11 — global, not tenant-scoped)."""
    name: str = Field(..., min_length=1)
    identification: str = Field(..., min_length=1)
    birth_date: Optional[date] = None
    city: Optional[str] = None
    department: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class DeliveryVehicleIn(BaseModel):
    """Vehicle fields a Distribuidor/superadmin may supply inline. Only
    `plate` is required — everything else may come from the VIN lookup
    (`vin_master_service.query_vin`, called AS-IS by
    `vehicle_service.register_or_update_vehicle` in PR4)."""
    plate: str = Field(..., min_length=1)
    vin: Optional[str] = None
    model: Optional[str] = None
    color: Optional[str] = None
    year: Optional[int] = None
    engine_number: Optional[str] = None


class DeliveryCreate(BaseModel):
    client: DeliveryClientIn
    vehicle: DeliveryVehicleIn
    delivery_date: date


class DeliveryOut(BaseModel):
    """The `Vehicle` row IS the delivery record (Design Decision 5) — this
    response converts directly off the returned ORM instance via
    `from_attributes`, same pattern as `HistoricalOrderOut`."""
    id: UUID
    plate: str
    vin: Optional[str] = None
    model: Optional[str] = None
    color: Optional[str] = None
    year: Optional[int] = None
    engine_number: Optional[str] = None
    delivery_date: Optional[date] = None
    delivery_act_url: Optional[str] = None
    client_id: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)
