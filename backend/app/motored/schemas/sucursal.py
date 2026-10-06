import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, field_validator

# ERP store code "C.O." (centro de operación): one region letter plus two
# digits (E05, C06). The ONE place the format lives, so relaxing it later
# is a one-line change.
CODIGO_CO_PATRON = re.compile(r"^[A-Z][0-9]{2}$")


def normalizar_codigo_co(valor: Any) -> Optional[str]:
    """Trimmed and upper-cased text; blank means "no code" (None). A number
    becomes its text, so it fails the format instead of being stored."""
    if valor is None:
        return None
    texto = str(valor).strip().upper()
    return texto or None


def motivo_codigo_co_invalido(codigo: Optional[str]) -> Optional[str]:
    """Why a normalized code breaks `CODIGO_CO_PATRON`, or None."""
    if codigo is None or CODIGO_CO_PATRON.match(codigo):
        return None
    return (
        f"Código C.O. '{codigo}' no es válido: debe ser una letra seguida "
        "de dos números (ej: E05)."
    )


def _validar_codigo_co(valor: Any) -> Optional[str]:
    codigo = normalizar_codigo_co(valor)
    motivo = motivo_codigo_co_invalido(codigo)
    if motivo:
        raise ValueError(motivo)
    return codigo


class SucursalCreate(BaseModel):
    nombre: str
    # ERP store code (centro de operación); unique across stores.
    codigo_co: Optional[str] = None
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
    # Form only: the store's final set of secondary bodega codes, saved
    # by the route (`bodegas_secundarias.guardar_de_sucursal`). None (or
    # omitted) leaves them as they are; [] releases them all.
    bodegas_secundarias: Optional[List[str]] = None

    _codigo_co = field_validator("codigo_co", mode="before")(
        _validar_codigo_co
    )


class SucursalUpdate(BaseModel):
    nombre: Optional[str] = None
    # Explicit null (or blank) clears it; omitted keeps the stored value.
    codigo_co: Optional[str] = None
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
    # Form only: the store's final set of secondary bodega codes, saved
    # by the route (`bodegas_secundarias.guardar_de_sucursal`). None (or
    # omitted) leaves them as they are; [] releases them all.
    bodegas_secundarias: Optional[List[str]] = None

    _codigo_co = field_validator("codigo_co", mode="before")(
        _validar_codigo_co
    )


class SucursalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    # NOT NULL in the database: every store has its C.O.
    codigo_co: str
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
    # The store's secondary bodega codes, filled by the routes that load
    # them (list, create, update); None = not loaded.
    bodegas_secundarias: Optional[List[str]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
