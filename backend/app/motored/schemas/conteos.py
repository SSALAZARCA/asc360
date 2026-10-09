"""
Inventory counts -- request and response shapes of the leader API and the
public pair API (odd/motored-conteos-inventario, WU6/WU7/WU8/WU9;
design §6.1, §6.2, §7, §8.3).

- No shape carries `codigo_hash`. The plain 6-digit code appears only in
  `IniciarSalida` and `CodigoSalida`, the two moments it exists.
- No shape carries a cédula: members are names only (Ley 1581).
- The public shapes carry no expected quantity, cost or difference: the
  count is blind (a test walks their OpenAPI schemas). The differences
  and the reconteo values are leader-only shapes.
"""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Dict, List, Literal, Optional, Tuple

from pydantic import (
    BaseModel, ConfigDict, Field, field_validator, model_validator,
)

from app.motored.models.conteo import ESTADOS, TIPOS
from app.motored.models.conteo_lectura import METODOS
from app.motored.schemas.vendedor import limpiar_cedula

EstadoConteo = Literal[ESTADOS]
TipoConteo = Literal[TIPOS]
FiltroDiferencias = Literal["todas", "criticas", "reconteo"]
LARGO_CEDULA = (4, 20)
MAX_LECTURAS_LOTE = 100
LARGO_NOMBRE_UBICACION = 60


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


# --- locations (leader and pair) ---------------------------------------------


def _nombre_ubicacion(valor: Optional[str]) -> Optional[str]:
    if valor is None:
        return None
    limpio = " ".join(valor.split())
    if not limpio:
        raise ValueError("nombre vacío")
    return limpio


class UbicacionPareja(BaseModel):
    id: uuid.UUID
    codigo: str
    nombre: str


class UbicacionLider(UbicacionPareja):
    activa: bool
    origen: str
    created_at: Optional[datetime] = None


class UbicacionCrear(BaseModel):
    """`codigo` may carry the label prefix `UBI-`; it is normalized."""

    codigo: str = Field(max_length=40)
    nombre: Optional[str] = Field(
        default=None, max_length=LARGO_NOMBRE_UBICACION)

    limpiar_nombre = field_validator("nombre")(_nombre_ubicacion)


class UbicacionEditar(BaseModel):
    nombre: Optional[str] = Field(
        default=None, max_length=LARGO_NOMBRE_UBICACION)
    activa: Optional[bool] = None

    limpiar_nombre = field_validator("nombre")(_nombre_ubicacion)

    @model_validator(mode="after")
    def _algo(self) -> "UbicacionEditar":
        if self.nombre is None and self.activa is None:
            raise ValueError("nada que cambiar")
        return self


class UbicacionFijar(BaseModel):
    """A typed code or a scanned `UBI-…` label; `nombre` names it when
    the store does not have it yet."""

    codigo: str = Field(max_length=40)
    nombre: Optional[str] = Field(
        default=None, max_length=LARGO_NOMBRE_UBICACION)


class UbicacionFijada(BaseModel):
    ubicacion: UbicacionPareja
    creada: bool


# --- readings (pair) ---------------------------------------------------------


class CatalogoSalida(BaseModel):
    """`referencias` is `[[code, name], ...]` (ADR-6)."""

    version: str
    referencias: List[Tuple[str, str]]


class LecturaEntrada(BaseModel):
    id: uuid.UUID
    codigo_leido: str = Field(max_length=120)
    cantidad: Decimal = Decimal("1")
    leida_en: datetime
    metodo: Literal[METODOS]
    forzar_desconocido: bool = False
    reconteo_id: Optional[uuid.UUID] = None

    @field_validator("leida_en")
    @classmethod
    def _con_zona(cls, valor: datetime) -> datetime:
        if valor.tzinfo is None:
            return valor.replace(tzinfo=timezone.utc)
        return valor


class LecturasEntrada(BaseModel):
    lecturas: List[LecturaEntrada] = Field(
        min_length=1, max_length=MAX_LECTURAS_LOTE)


class CodigoDesconocido(BaseModel):
    id: uuid.UUID
    codigo: str


class LecturaRechazada(BaseModel):
    id: uuid.UUID
    motivo: str


class LecturasSalida(BaseModel):
    """`aceptadas` were stored now; `duplicadas` were already stored (a
    resend). `desconocidos` were NOT stored: resend them with
    `forzar_desconocido` to keep them. `referencias`: code -> name."""

    aceptadas: List[uuid.UUID]
    duplicadas: List[uuid.UUID]
    desconocidos: List[CodigoDesconocido]
    rechazadas: List[LecturaRechazada]
    referencias: Dict[str, str]


class AnulacionSalida(BaseModel):
    id: uuid.UUID
    anulada_en: datetime


class UbicacionCorta(BaseModel):
    codigo: str
    nombre: str


class LecturaPareja(BaseModel):
    id: uuid.UUID
    codigo: str
    descripcion: Optional[str] = None
    cantidad: Decimal
    metodo: str
    ubicacion: UbicacionCorta
    leida_en: datetime
    anulada_en: Optional[datetime] = None


class ResumenUbicacion(BaseModel):
    """What THIS session counted of one code in its current location."""

    codigo: str
    descripcion: Optional[str] = None
    cantidad: Decimal
    lecturas: int


class RecientesSalida(BaseModel):
    ubicacion_actual: Optional[UbicacionPareja] = None
    lecturas: List[LecturaPareja]
    resumen_ubicacion: List[ResumenUbicacion]


# --- reconteo: leader (WU9) --------------------------------------------------


class ReconteoManualEntrada(BaseModel):
    codigo: str = Field(min_length=1, max_length=120)


class AsignarEntrada(BaseModel):
    sesion_id: uuid.UUID
    autorizar_misma_pareja: bool = False
    motivo: Optional[str] = Field(default=None, max_length=2000)


class FinRondaSalida(BaseModel):
    estado: str
    ronda_terminada_en: Optional[datetime] = None
    diferencias: int
    reconteos_creados: int


class SesionCorta(BaseModel):
    id: uuid.UUID
    etiqueta: str


class ReconteoEnDiferencia(BaseModel):
    id: uuid.UUID
    estado: str
    origen: str
    sesion: Optional[SesionCorta] = None
    misma_pareja_autorizada: bool = False


class DiferenciaSalida(BaseModel):
    """One code (leader-only). `contado` is the final quantity: the
    finished reconteo's, else round 1's."""

    referencia_id: Optional[uuid.UUID] = None
    codigo: str
    descripcion: Optional[str] = None
    ubicaciones: List[str]
    sistema: Decimal
    contado_ronda1: Decimal
    contado: Decimal
    diferencia: Decimal
    costo_unitario: Optional[Decimal] = None
    sin_costo: bool
    valor: Optional[Decimal] = None
    critico: bool
    reconteo: Optional[ReconteoEnDiferencia] = None


class DiferenciasSalida(BaseModel):
    """`parcial` while round 1 is open; the counts cover every
    difference, `items` only the filtered ones."""

    estado: str
    parcial: bool
    umbrales: UmbralesSalida
    total: int
    criticas: int
    en_reconteo: int
    items: List[DiferenciaSalida]


class ReconteoLider(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    referencia_id: Optional[uuid.UUID] = None
    estado: str
    origen: str
    diferencia_ronda1: Optional[Decimal] = None
    valor_ronda1: Optional[Decimal] = None
    sesion_id: Optional[uuid.UUID] = None
    misma_pareja_autorizada: bool = False
    motivo_autorizacion: Optional[str] = None
    asignado_en: Optional[datetime] = None
    terminado_en: Optional[datetime] = None
    cancelado_en: Optional[datetime] = None


class RepartoSalida(BaseModel):
    asignados: List[ReconteoLider]
    sin_pareja: List[ReconteoLider]


# --- reconteo: pair (WU9, blind) ---------------------------------------------


class ReconteoTarea(BaseModel):
    """Where round 1 found the code; never a quantity."""

    id: uuid.UUID
    codigo: str
    descripcion: Optional[str] = None
    ubicaciones: List[str]
    estado: str


class ReconteoTerminado(BaseModel):
    id: uuid.UUID
    estado: str
    terminado_en: Optional[datetime] = None
