import uuid
from datetime import date
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict

from app.motored.services.fechas_utc import UtcDatetime


class ParametroMetodologiaCreate(BaseModel):
    clave: str
    valor: Any
    vigente_desde: date
    # None = alcance global. Sólo `dias_entre_pedidos` admite sucursal.
    sucursal_id: Optional[uuid.UUID] = None


class ParametroMetodologiaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    clave: str
    valor: Any
    vigente_desde: date
    sucursal_id: Optional[uuid.UUID] = None
    created_at: Optional[UtcDatetime] = None


class HistorialParametro(BaseModel):
    """Una versión de una clave, para el cajón de historial."""

    id: uuid.UUID
    clave: str
    valor: Any
    vigente_desde: date
    sucursal_id: Optional[uuid.UUID] = None
    created_by: Optional[uuid.UUID] = None
    created_by_nombre: Optional[str] = None
    created_at: Optional[UtcDatetime] = None


class ConfiguracionEfectivo(BaseModel):
    valor: Any
    fuente: str
    parametro_id: Optional[uuid.UUID] = None
    vigente_desde: Optional[date] = None


class ConfiguracionSucursal(BaseModel):
    sucursal_id: uuid.UUID
    valor: Any
    vigente_desde: date
    parametro_id: uuid.UUID


class ConfiguracionProgramada(BaseModel):
    valor: Any
    vigente_desde: date
    sucursal_id: Optional[uuid.UUID] = None


class ConfiguracionClave(BaseModel):
    clave: str
    seccion: str
    grupo: str
    tipo: str
    dominio: str
    ambito: str
    default: Any = None
    opciones: List[str] = []
    minimo: Optional[Any] = None
    maximo: Optional[Any] = None
    minimo_exclusivo: bool = False
    campos: List[str] = []
    snapshotted: bool
    efectivo_global: ConfiguracionEfectivo
    por_sucursal: List[ConfiguracionSucursal] = []
    programados: List[ConfiguracionProgramada] = []


class ConfiguracionGrupo(BaseModel):
    grupo: str
    claves: List[ConfiguracionClave]


class ConfiguracionSeccion(BaseModel):
    seccion: str
    grupos: List[ConfiguracionGrupo]


class ConfiguracionRespuesta(BaseModel):
    secciones: List[ConfiguracionSeccion]
