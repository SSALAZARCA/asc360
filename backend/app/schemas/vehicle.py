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
    tenant_id: UUID

class VehicleUpdate(VehicleBase):
    plate: Optional[str] = None
    tenant_id: Optional[UUID] = None

from typing import Optional, Any, List

class VehicleOut(VehicleBase):
    id: UUID
    tenant_id: UUID
    client: Optional[Any] = None
    client_id: Optional[UUID] = None
    latest_mileage: Optional[int] = None
    active_order: Optional[Any] = None
    service_orders_summary: Optional[List[Any]] = None

    model_config = ConfigDict(from_attributes=True)
