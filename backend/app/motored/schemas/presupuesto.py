"""
Motored budgets (odd/motored-presupuestos-gerencia, T2): request and response
schemas of `/presupuestos`. Money is integer pesos; months are `YYYY-MM`.
"""
import uuid
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class PresupuestoAsesorEdit(BaseModel):
    """Manual add/change of ONE asesor's budget for a month."""
    sucursal_id: uuid.UUID
    monto: int = Field(gt=0)
    nota: Optional[str] = Field(default=None, max_length=500)

    @field_validator("nota")
    @classmethod
    def _nota_vacia_es_none(cls, valor):
        return (valor or "").strip() or None


class IncidenciaOut(BaseModel):
    fila: int
    columna: str
    mensaje: str


class TiendaTotalOut(BaseModel):
    sucursal_id: str
    tienda: str
    asesores: int
    total: int


class ResumenMesOut(BaseModel):
    mes: str
    asesores: int
    total: int
    reemplaza_version: Optional[int] = None
    por_tienda: List[TiendaTotalOut]


class ValidacionOut(BaseModel):
    valido: bool
    filas: int
    meses: List[ResumenMesOut]
    errores: List[IncidenciaOut]
    warnings: List[IncidenciaOut]


class AplicadoMesOut(BaseModel):
    mes: str
    version: int
    asesores: int
    total: int


class AplicadoOut(BaseModel):
    meses: List[AplicadoMesOut]


class VersionCreadaOut(BaseModel):
    mes: str
    version: int


class MesListadoOut(BaseModel):
    mes: str
    version: int
    origen: str
    created_at: str
    asesores: int
    total: int


class LineaOut(BaseModel):
    cedula: str
    asesor: str
    sucursal_id: str
    tienda: str
    monto: int


class VersionDetalleOut(BaseModel):
    id: str
    mes: str
    version: int
    origen: str
    archivo_nombre: Optional[str] = None
    nota: Optional[str] = None
    created_at: str
    asesores: int
    total: int
    lineas: List[LineaOut]
    por_tienda: List[TiendaTotalOut]


class VersionHistorialOut(BaseModel):
    id: str
    version: int
    origen: str
    archivo_nombre: Optional[str] = None
    nota: Optional[str] = None
    created_at: str
    created_by_nombre: Optional[str] = None
    lineas: int
    total: int
