import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class SucursalCreate(BaseModel):
    nombre: str
    sic: Optional[str] = None
    dias_seguridad: Decimal = Decimal("2.5")


class SucursalUpdate(BaseModel):
    nombre: Optional[str] = None
    sic: Optional[str] = None
    dias_seguridad: Optional[Decimal] = None


class SucursalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    sic: Optional[str] = None
    dias_seguridad: Decimal
    activa: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
