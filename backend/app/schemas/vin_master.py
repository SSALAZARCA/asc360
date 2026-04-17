from pydantic import BaseModel, ConfigDict
from typing import Optional
from uuid import UUID

class VinMasterBase(BaseModel):
    vin: str
    engine_number: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    color: Optional[str] = None
    displacement: Optional[str] = None
    warranty_status: Optional[str] = None
    expected_reviews: Optional[int] = None
    completed_reviews: Optional[int] = None

class VinMasterCreate(VinMasterBase):
    pass

class VinMasterUpdate(VinMasterBase):
    vin: Optional[str] = None # Aunque no se debería cambiar el VIN, pydantic lo permite como opcional en update

class VinMasterOut(VinMasterBase):
    id: UUID

    model_config = ConfigDict(from_attributes=True)
