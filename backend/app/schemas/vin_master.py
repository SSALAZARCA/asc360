from pydantic import BaseModel, ConfigDict, Field
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
    vin: Optional[str] = None  # Aunque no se debería cambiar el VIN, pydantic lo permite como opcional en update


# Serializes a `ShipmentMotoUnit` row (see `vin_master_service.query_vin`),
# NOT the dead `VinMaster` model -- that table is never populated by any
# import flow, so every lookup against it 404'd regardless of the VIN. Kept
# independent of `VinMasterBase` so it only ever describes real columns.
# `validation_alias` (not `alias`) so these read the ORM's real attribute
# names while still serializing to the plain JSON keys callers expect.
class VinMasterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vin: str = Field(validation_alias="vin_number")
    engine_number: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = Field(None, validation_alias="model_year")
    color: Optional[str] = Field(None, validation_alias="color_runt")
