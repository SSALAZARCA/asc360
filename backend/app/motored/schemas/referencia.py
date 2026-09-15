import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ReferenciaCreate(BaseModel):
    codigo: str
    proveedor_id: uuid.UUID
    descripcion: Optional[str] = None
    unidad_empaque: Optional[int] = None
    precio_normal: Optional[Decimal] = None
    precio_venta: Optional[Decimal] = None
    precio_publico: Optional[Decimal] = None
    sustituida_por: Optional[uuid.UUID] = None


class ReferenciaUpdate(BaseModel):
    descripcion: Optional[str] = None
    unidad_empaque: Optional[int] = None
    precio_normal: Optional[Decimal] = None
    precio_venta: Optional[Decimal] = None
    precio_publico: Optional[Decimal] = None
    sustituida_por: Optional[uuid.UUID] = None


class ReferenciaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    proveedor_id: uuid.UUID
    descripcion: Optional[str] = None
    unidad_empaque: int
    unidad_empaque_advertencia: bool
    precio_normal: Optional[Decimal] = None
    precio_venta: Optional[Decimal] = None
    precio_publico: Optional[Decimal] = None
    sustituida_por: Optional[uuid.UUID] = None
    activa: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
