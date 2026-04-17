from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID
from typing import Optional

# ----------------- LIMITED WARRANTIES -----------------
class VehicleLimitedWarrantyBase(BaseModel):
    model_code: Optional[str] = Field(None, max_length=50, description="Model ID or ALL")
    component_name: str = Field(..., min_length=2, max_length=100, description="Name of the part")
    covered_km: int = Field(..., ge=0, description="Kilometers of coverage")
    covered_days: int = Field(..., ge=0, description="Days of coverage")
    exclusion_notes: Optional[str] = Field(None, max_length=500)

class VehicleLimitedWarrantyCreate(VehicleLimitedWarrantyBase):
    pass

class VehicleLimitedWarrantyRead(VehicleLimitedWarrantyBase):
    id: UUID
    model_config = ConfigDict(from_attributes=True)

# ----------------- REVIEW SCHEDULES -----------------
class MandatoryMaintenanceScheduleBase(BaseModel):
    model_code: Optional[str] = Field(None, description="Applies to specific model or 'ALL'")
    maintenance_number: int = Field(..., ge=1, description="Chronological order of the maintenance 1, 2, 3...")
    km_target: int = Field(..., ge=0, description="Target mileage")
    tolerance_pre_km: int = Field(100, ge=0)
    tolerance_post_km: int = Field(200, ge=0)
    is_free_labor: bool = False

class MandatoryMaintenanceScheduleCreate(MandatoryMaintenanceScheduleBase):
    pass

class MandatoryMaintenanceScheduleRead(MandatoryMaintenanceScheduleBase):
    id: UUID
    model_config = ConfigDict(from_attributes=True)
