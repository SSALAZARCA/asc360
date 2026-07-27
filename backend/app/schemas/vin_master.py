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
    vin: Optional[str] = None # Aunque no se debería cambiar el VIN, pydantic lo permite como opcional en update

# NOT `VinMasterBase` -- that schema's `model`/`brand`/`displacement`/
# `warranty_status`/`expected_reviews`/`completed_reviews` fields don't match
# any column on the `VinMaster` ORM model (which only has `model_name`,
# `model_code`, no brand at all). With `from_attributes=True` that mismatch
# crashes serialization on any real match. This is the schema actually
# returned by `GET /vehicles/vin/{vin}`, kept independent of the Base so it
# only ever describes real columns.
class VinMasterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vin: str
    engine_number: Optional[str] = None
    # `validation_alias` (not `alias`) so this reads `.model_name` off the ORM
    # row but still serializes to the plain `"model"` JSON key callers expect.
    model: Optional[str] = Field(None, validation_alias="model_name")
    year: Optional[int] = None
    color: Optional[str] = None
