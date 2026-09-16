import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ProveedorCreate(BaseModel):
    codigo: str
    nombre: str
    es_principal: bool = False
    dias_empaque_default: Optional[int] = None
    dias_transito_default: Optional[int] = None
    dias_seguridad_default: Optional[Decimal] = Decimal("2.5")


class ProveedorUpdate(BaseModel):
    nombre: Optional[str] = None
    es_principal: Optional[bool] = None
    dias_empaque_default: Optional[int] = None
    dias_transito_default: Optional[int] = None
    dias_seguridad_default: Optional[Decimal] = None


class ProveedorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    nombre: str
    es_principal: bool
    dias_empaque_default: Optional[int] = None
    dias_transito_default: Optional[int] = None
    dias_seguridad_default: Optional[Decimal] = None
    activa: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
