import re
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

_ESPACIOS_RE = re.compile(r"\s+")
_FLOAT_ENTERO_RE = re.compile(r"^(\d+)\.0+$")


def _limpiar_nombre(valor):
    if valor is None:
        return valor
    texto = _ESPACIOS_RE.sub(" ", str(valor)).strip()
    if not texto:
        raise ValueError("No puede estar vacío")
    return texto


def _normalizar_cargo(valor):
    """Texto libre del negocio, pero en MAYUSCULAS y sin espacios de mas: asi
    "Asesor de repuestos" y "ASESOR DE REPUESTOS" agrupan igual en el tablero."""
    texto = _limpiar_nombre(valor)
    return texto.upper() if texto is not None else texto


def _limpiar_cedula(valor):
    """Una cedula leida de Excel como numero llega como `123.0`: se le quita el
    decimal. Vacia = no provista."""
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    coincide = _FLOAT_ENTERO_RE.match(texto)
    return coincide.group(1) if coincide else texto


class VendedorCreate(BaseModel):
    nombre: str = Field(max_length=255)
    cargo: str = Field(max_length=80)
    sucursal_id: Optional[uuid.UUID] = None
    cedula: Optional[str] = Field(default=None, max_length=20)
    usuario_id: Optional[uuid.UUID] = None
    activo: bool = True

    _nombre = field_validator("nombre", mode="before")(_limpiar_nombre)
    _cargo = field_validator("cargo", mode="before")(_normalizar_cargo)
    _cedula = field_validator("cedula", mode="before")(_limpiar_cedula)


class VendedorUpdate(BaseModel):
    nombre: Optional[str] = Field(default=None, max_length=255)
    cargo: Optional[str] = Field(default=None, max_length=80)
    sucursal_id: Optional[uuid.UUID] = None
    cedula: Optional[str] = Field(default=None, max_length=20)
    usuario_id: Optional[uuid.UUID] = None
    activo: Optional[bool] = None

    _nombre = field_validator("nombre", mode="before")(_limpiar_nombre)
    _cargo = field_validator("cargo", mode="before")(_normalizar_cargo)
    _cedula = field_validator("cedula", mode="before")(_limpiar_cedula)


class VendedorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    nombre_norm: str
    cargo: str
    sucursal_id: Optional[uuid.UUID] = None
    cedula: Optional[str] = None
    usuario_id: Optional[uuid.UUID] = None
    activo: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
