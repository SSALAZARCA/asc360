"""
Inventory counts -- request and response shapes of the leader API and the
public pair API (odd/motored-conteos-inventario, WU6/WU7; design §6.1,
§6.2, §8.3).

- No shape carries `codigo_hash`. The plain 6-digit code appears only in
  `IniciarSalida` and `CodigoSalida`, the two moments it exists.
- No shape carries a cédula: members are names only (Ley 1581).
- The public shapes (`UnirseSalida`, `SesionPareja`) carry no expected
  quantity, cost or difference: the count is blind.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.motored.models.conteo import ESTADOS, TIPOS
from app.motored.schemas.vendedor import limpiar_cedula

EstadoConteo = Literal[ESTADOS]
TipoConteo = Literal[TIPOS]
LARGO_CEDULA = (4, 20)


# --- leader API: requests ----------------------------------------------------


class ProgramarEntrada(BaseModel):
    sucursal_id: uuid.UUID
    lider_id: uuid.UUID
    fecha_programada: date


class ReprogramarEntrada(BaseModel):
    fecha_programada: date
    lider_id: Optional[uuid.UUID] = None


class AnularEntrada(BaseModel):
    motivo: Optional[str] = Field(default=None, max_length=2000)


class IniciarEntrada(BaseModel):
    confirmar_antiguedad: bool = False


# --- leader API: responses ---------------------------------------------------


class Nombrado(BaseModel):
    id: uuid.UUID
    nombre: str


class UmbralesSalida(BaseModel):
    reconteo: Optional[Decimal] = None
    critico: Optional[Decimal] = None


class SnapshotSalida(BaseModel):
    carga_id: Optional[uuid.UUID] = None
    nombre_archivo: Optional[str] = None
    fecha_corte: Optional[date] = None
    aplicado_en: Optional[datetime] = None
    tomado_en: Optional[datetime] = None
    lineas: int = 0
    valor_sistema: Optional[Decimal] = None
    sin_costo: int = 0
    advertencias: Optional[dict] = None


class AccesoSalida(BaseModel):
    slug: str
    url: Optional[str] = None
    qr_url: str
    codigo_rotado_en: Optional[datetime] = None


class ConteoResumen(BaseModel):
    id: uuid.UUID
    tipo: str
    estado: str
    origen: str
    fecha_programada: date
    sucursal: Nombrado
    lider: Optional[Nombrado] = None
    iniciado_en: Optional[datetime] = None
    cerrado_en: Optional[datetime] = None
    anulado_en: Optional[datetime] = None
    motivo_anulacion: Optional[str] = None
    created_at: Optional[datetime] = None


class ConteoDetalle(ConteoResumen):
    snapshot: Optional[SnapshotSalida] = None
    umbrales: UmbralesSalida
    acceso: Optional[AccesoSalida] = None


class IniciarSalida(BaseModel):
    conteo: ConteoDetalle
    codigo: str
    advertencia: Optional[dict] = None


class CodigoSalida(BaseModel):
    codigo: str
    rotado_en: Optional[datetime] = None


class LiderOpcion(BaseModel):
    id: uuid.UUID
    nombre: str
    email: Optional[str] = None


class InventarioSalida(BaseModel):
    carga_id: uuid.UUID
    fecha_corte: date
    aplicado_en: Optional[datetime] = None
    antiguedad_horas: Decimal


class SucursalOpcion(BaseModel):
    id: uuid.UUID
    nombre: str
    inventario: Optional[InventarioSalida] = None
    vigencia_horas: Optional[int] = None


class UbicacionSalida(BaseModel):
    id: uuid.UUID
    nombre: str


class SesionLider(BaseModel):
    id: uuid.UUID
    numero: int
    etiqueta: str
    estado: str
    dispositivo: str
    integrantes: List[str]
    ubicacion_actual: Optional[UbicacionSalida] = None
    conectada_en: Optional[datetime] = None
    ultima_actividad_en: Optional[datetime] = None
    desconectada_en: Optional[datetime] = None


# --- public pair API ---------------------------------------------------------


class IntegranteEntrada(BaseModel):
    nombre: str = Field(max_length=120)
    cedula: str = Field(max_length=40)

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, valor: str) -> str:
        limpio = " ".join(valor.split())
        if len(limpio) < 2:
            raise ValueError("nombre vacío")
        return limpio

    @field_validator("cedula")
    @classmethod
    def _cedula(cls, valor: str) -> str:
        limpia = limpiar_cedula(valor)
        minimo, maximo = LARGO_CEDULA
        if not minimo <= len(limpia) <= maximo:
            raise ValueError("cédula con largo inválido")
        return limpia


class UnirseEntrada(BaseModel):
    """Read by hand from the body (see `api/publico_conteos.py`), so a
    validation error never echoes a cédula back."""

    codigo: str = Field(max_length=20)
    dispositivo: Literal["ESCRITORIO", "MOVIL"] = "ESCRITORIO"
    integrantes: List[IntegranteEntrada] = Field(
        min_length=2, max_length=3)

    @model_validator(mode="after")
    def _cedulas_distintas(self) -> "UnirseEntrada":
        cedulas = [i.cedula for i in self.integrantes]
        if len(set(cedulas)) != len(cedulas):
            raise ValueError("cédulas repetidas")
        return self


class UnirseSalida(BaseModel):
    sesion_token: str
    sesion_id: uuid.UUID
    etiqueta: str
    integrantes: List[str]
    sucursal: str
    estado_conteo: str


class SesionPareja(BaseModel):
    sesion_id: uuid.UUID
    etiqueta: str
    integrantes: List[str]
    sucursal: str
    estado_conteo: str
    ubicacion_actual: Optional[UbicacionSalida] = None
