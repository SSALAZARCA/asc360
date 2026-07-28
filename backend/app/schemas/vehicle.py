from pydantic import BaseModel, ConfigDict
from typing import Optional
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

from typing import Optional, Any, List

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
    client: Optional[Any] = None
    client_id: Optional[UUID] = None
    latest_mileage: Optional[int] = None
    active_order: Optional[Any] = None
    service_orders_summary: Optional[List[Any]] = None

    model_config = ConfigDict(from_attributes=True)
