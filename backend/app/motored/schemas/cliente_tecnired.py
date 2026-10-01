import re
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

_ESPACIOS_RE = re.compile(r"\s+")
_FLOAT_ENTERO_RE = re.compile(r"^(\d+)\.0+$")


def normalizar_nit(crudo: str) -> str:
    """Misma regla que la columna CLIENTE NORMALIZADO del Excel de origen
    (`IF(RIGHT(TRIM(x),1)=".", LEFT(...), TRIM(x))`): recorta, saca el punto
    final. Ademas se quitan los espacios internos y el `.0` que deja un
    numero entero leido como decimal desde Excel (`900123456.0`).

    Es idempotente (`f(f(x)) == f(x)`): se aplica al cargar la lista y otra
    vez al cruzar con las ventas, asi que se repite hasta que no cambia
    (`123.0.` -> `123.0` -> `123`)."""
    texto = _ESPACIOS_RE.sub("", str(crudo))
    while True:
        coincide = _FLOAT_ENTERO_RE.match(texto)
        if coincide:
            siguiente = coincide.group(1)
        elif texto.endswith("."):
            siguiente = texto[:-1]
        else:
            return texto
        texto = siguiente


class ClienteTecniredCreate(BaseModel):
    nit: str = Field(max_length=30)
    razon_social: Optional[str] = Field(default=None, max_length=255)

    @field_validator("nit", mode="before")
    @classmethod
    def _normalizar_nit(cls, valor):
        if valor is None:
            raise ValueError("El NIT es obligatorio")
        normalizado = normalizar_nit(valor)
        if not normalizado:
            raise ValueError("El NIT quedó vacío después de limpiarlo")
        return normalizado

    @field_validator("razon_social", mode="before")
    @classmethod
    def _limpiar_razon_social(cls, valor):
        if valor is None:
            return None
        texto = str(valor).strip()
        return texto or None


class ClienteTecniredRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nit: str
    razon_social: Optional[str] = None
    created_at: Optional[datetime] = None
