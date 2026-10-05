import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class SucursalCreate(BaseModel):
    nombre: str
    sic: Optional[str] = None
    dias_seguridad: Decimal = Decimal("2.5")
    dias_empaque: Optional[int] = None
    dias_transito: Optional[int] = None
    bodega_principal: Optional[str] = None
    departamento: Optional[str] = None
    ciudad: Optional[str] = None
    fecha_apertura: Optional[date] = None
    # None = not provided: a new store is created active.
    activa: Optional[bool] = None
    # Principal store this one rolls up into; None = its own principal.
    principal_id: Optional[uuid.UUID] = None


class SucursalUpdate(BaseModel):
    nombre: Optional[str] = None
    sic: Optional[str] = None
    dias_seguridad: Optional[Decimal] = None
    dias_empaque: Optional[int] = None
    dias_transito: Optional[int] = None
    bodega_principal: Optional[str] = None
    departamento: Optional[str] = None
    ciudad: Optional[str] = None
    fecha_apertura: Optional[date] = None
    activa: Optional[bool] = None
    # Explicit null dissociates; omitted keeps the stored value.
    principal_id: Optional[uuid.UUID] = None


class SucursalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    sic: Optional[str] = None
    dias_seguridad: Decimal
    dias_empaque: Optional[int] = None
    dias_transito: Optional[int] = None
    bodega_principal: Optional[str] = None
    departamento: Optional[str] = None
    ciudad: Optional[str] = None
    fecha_apertura: Optional[date] = None
    activa: bool
    principal_id: Optional[uuid.UUID] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
