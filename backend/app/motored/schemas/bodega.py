import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class BodegaCreate(BaseModel):
    codigo: str
    descripcion: Optional[str] = None
    sucursal_id: Optional[uuid.UUID] = None
    bodega_principal: Optional[str] = None


class BodegaUpdate(BaseModel):
    descripcion: Optional[str] = None
    sucursal_id: Optional[uuid.UUID] = None
    bodega_principal: Optional[str] = None


class BodegaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    descripcion: Optional[str] = None
    sucursal_id: Optional[uuid.UUID] = None
    bodega_principal: Optional[str] = None
    activa: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
