"""
Referencia schemas.

Business-facing field layout (owner request 2026-09-28), in this order:
Código, Código del proveedor, Nombre, Línea comercial, Unidad de empaque,
Precio Normal antes de IVA, Precio Público antes de IVA, Código de referencia
sustituta, Homologados otras marcas.

`precio_venta` is no longer part of that layout (template, bulk parser, UI),
but the DB column is kept, so the schemas still accept/return it for
backward compatibility.

`homologados` is multi-value: a string ("A; B, C") or a list is normalized by
`texto.split_multivalor` (split on comma/semicolon, trim, drop empties,
dedupe preserving order). The DB column is NOT NULL with an empty-array
default, so `None` always normalizes to `[]`.
"""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.motored.services.texto import split_multivalor


HOMOLOGADO_MAX_LENGTH = 100  # matches `ARRAY(String(100))` on the model
HOMOLOGADOS_MAX_ITEMS = 50


class _HomologadosMixin(BaseModel):
    homologados: List[str] = Field(default_factory=list)

    @field_validator("homologados", mode="before")
    @classmethod
    def _normalize_homologados(cls, value: Any) -> List[str]:
        valores = split_multivalor(value)
        if len(valores) > HOMOLOGADOS_MAX_ITEMS:
            raise ValueError(
                f"'Homologados otras marcas' admite máximo {HOMOLOGADOS_MAX_ITEMS} valores "
                f"(se recibieron {len(valores)})"
            )
        demasiado_largos = [v for v in valores if len(v) > HOMOLOGADO_MAX_LENGTH]
        if demasiado_largos:
            # Rejected here (validation time) instead of letting Postgres fail
            # at commit time, which would surface as a 500 after the
            # all-or-nothing check already passed.
            raise ValueError(
                f"cada homologado admite máximo {HOMOLOGADO_MAX_LENGTH} caracteres: '{demasiado_largos[0][:30]}...'"
            )
        return valores


class ReferenciaCreate(_HomologadosMixin):
    codigo: str
    proveedor_id: uuid.UUID
    nombre: Optional[str] = None
    linea_comercial: Optional[str] = None
    unidad_empaque: Optional[int] = None
    precio_normal: Optional[Decimal] = None
    precio_venta: Optional[Decimal] = None
    precio_publico: Optional[Decimal] = None
    sustituida_por: Optional[uuid.UUID] = None


class ReferenciaUpdate(_HomologadosMixin):
    nombre: Optional[str] = None
    linea_comercial: Optional[str] = None
    unidad_empaque: Optional[int] = None
    precio_normal: Optional[Decimal] = None
    precio_venta: Optional[Decimal] = None
    precio_publico: Optional[Decimal] = None
    sustituida_por: Optional[uuid.UUID] = None


class ReferenciaRead(_HomologadosMixin):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    proveedor_id: uuid.UUID
    nombre: Optional[str] = None
    linea_comercial: Optional[str] = None
    unidad_empaque: int
    unidad_empaque_advertencia: bool
    precio_normal: Optional[Decimal] = None
    precio_venta: Optional[Decimal] = None
    precio_publico: Optional[Decimal] = None
    sustituida_por: Optional[uuid.UUID] = None
    activa: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
