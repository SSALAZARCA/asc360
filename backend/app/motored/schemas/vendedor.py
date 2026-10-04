import re
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

_ESPACIOS_RE = re.compile(r"\s+")
_DECIMAL_CERO_RE = re.compile(r"\.0$")
_SEPARADORES_RE = re.compile(r"[\s.]+")


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


def limpiar_cedula(valor):
    """Cedula = solo digitos. Una cedula leida de Excel como numero llega como
    `123.0` (se le quita ese decimal) y las escritas con puntos o espacios
    ("1.130.123.456") se compactan. Es obligatoria: vacia o con letras se rechaza."""
    texto = "" if valor is None else str(valor).strip()
    texto = _DECIMAL_CERO_RE.sub("", texto)
    texto = _SEPARADORES_RE.sub("", texto)
    if not texto:
        raise ValueError("La cédula es obligatoria")
    if not texto.isascii() or not texto.isdigit():
        raise ValueError("La cédula debe tener solo números (sin letras ni guiones)")
    return texto


def normalizar_cargo_de_fila(valor) -> str:
    """Mismo cargo que quedaria guardado (mayusculas, sin espacios de mas)."""
    return _normalizar_cargo(valor)


class VendedorCreate(BaseModel):
    nombre: str = Field(max_length=255)
    cargo: str = Field(max_length=80)
    sucursal_id: Optional[uuid.UUID] = None
    # Obligatoria: `validate_default` hace que omitirla tambien dispare el
    # validador y de el mensaje en español (la columna sigue nullable en la base).
    cedula: Optional[str] = Field(default=None, max_length=20, validate_default=True)
    usuario_id: Optional[uuid.UUID] = None
    activo: bool = True

    _nombre = field_validator("nombre", mode="before")(_limpiar_nombre)
    _cargo = field_validator("cargo", mode="before")(_normalizar_cargo)
    _cedula = field_validator("cedula", mode="before")(limpiar_cedula)


class VendedorUpdate(BaseModel):
    nombre: Optional[str] = Field(default=None, max_length=255)
    cargo: Optional[str] = Field(default=None, max_length=80)
    sucursal_id: Optional[uuid.UUID] = None
    cedula: Optional[str] = Field(default=None, max_length=20)
    usuario_id: Optional[uuid.UUID] = None
    activo: Optional[bool] = None

    _nombre = field_validator("nombre", mode="before")(_limpiar_nombre)
    _cargo = field_validator("cargo", mode="before")(_normalizar_cargo)
    _cedula = field_validator("cedula", mode="before")(limpiar_cedula)


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
