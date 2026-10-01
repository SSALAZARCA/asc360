"""
Motored Pedidos F4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B2, B3a,
ADR-1, ADR-3): esquemas de la edición de líneas y su historial y del ciclo de
vida del pedido por tienda (cerrar, reabrir, cabecera y eventos).

`pedido_final` entra SIN tipo (`Any`): la regla de E-CORRIDA-053 la aplica el
servicio, DESPUÉS de los chequeos de estado (404, 042, 065, 052), así un valor
inválido siempre responde con su código y no con el 422 genérico del
validador. Los campos extra se prohíben (no se acepta Z ni nada más). Igual
el `motivo` de reabrir (E-CORRIDA-046).
"""
import datetime
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.motored.schemas.corrida import (
    AccionesTienda,
    LineaRead,
    UltimoEvento,
)


class LineaEditar(BaseModel):
    """Cuerpo de `PATCH /corridas/{id}/lineas/{linea_id}`. `esperado` es la
    cantidad que la pantalla vio: si cambió mientras tanto, E-CORRIDA-066."""

    model_config = ConfigDict(extra="forbid")

    pedido_final: Any = None
    esperado: Optional[Decimal] = None


class TotalesTienda(BaseModel):
    """Lo que se va a pedir en la tienda junto al sugerido del motor."""

    unidades_a_pedir: Decimal
    valor_a_pedir: Decimal
    unidades_sugerido: Decimal
    valor_sugerido: Decimal


class LineaEditada(BaseModel):
    """Respuesta del PATCH: la línea ya refrescada y los totales."""

    linea: LineaRead
    totales_tienda: TotalesTienda


class HistorialLinea(BaseModel):
    """Una fila inmutable del historial de una línea."""

    id: int
    linea_id: int
    campo: str
    valor_anterior: Decimal
    valor_nuevo: Decimal
    motivo: str
    detalle: Optional[Dict[str, Any]] = None
    usuario_id: uuid.UUID
    usuario: str
    creado_en: datetime.datetime


# --- Ciclo de vida del pedido por tienda (B3a) ------------------------------


class CerrarLote(BaseModel):
    """Cuerpo (opcional) de `POST /corridas/{id}/cerrar`. Sin cuerpo cierra
    todas las tiendas que sigan en BORRADOR; con `sucursal_ids`, sólo esas,
    todo o nada. Una lista vacía se rechaza: nunca se lee como "todas"."""

    model_config = ConfigDict(extra="forbid")

    sucursal_ids: Optional[List[uuid.UUID]] = Field(None, min_length=1)


class CierreLote(BaseModel):
    """Respuesta del cierre por lote: un superconjunto de `CorridaEstado`
    (`estado` es el del cálculo, no cambia). `ya_cerradas` cuenta las tiendas
    OK que ya estaban CERRADO o ENVIADO (sólo sin lista)."""

    id: uuid.UUID
    codigo: str
    estado: str
    cerradas: List[uuid.UUID]
    ya_cerradas: int


class ReabrirCuerpo(BaseModel):
    """Cuerpo de `POST .../sucursales/{sid}/reabrir`."""

    model_config = ConfigDict(extra="forbid")

    motivo: Any = None


class EstadoPedidoTienda(BaseModel):
    """Respuesta de cerrar o reabrir UNA tienda."""

    corrida_id: uuid.UUID
    sucursal_id: uuid.UUID
    estado_pedido: str


class CabeceraTienda(BaseModel):
    """La cabecera de la pantalla del pedido de una tienda."""

    corrida_id: uuid.UUID
    corrida_codigo: str
    fecha_corte: datetime.date
    corrida_estado: str
    es_escenario: bool
    invalidada: bool
    sucursal_id: uuid.UUID
    nombre: str
    sic: Optional[str] = None
    estado: str
    codigo: Optional[str] = None
    mensaje: Optional[str] = None
    estado_pedido: Optional[str] = None
    totales: TotalesTienda
    ultimo_evento: Optional[UltimoEvento] = None
    acciones: AccionesTienda


class EventoPedido(BaseModel):
    """Una fila de la línea de tiempo del pedido de una tienda."""

    id: int
    evento: str
    motivo: Optional[str] = None
    detalle: Optional[Dict[str, Any]] = None
    usuario_id: Optional[uuid.UUID] = None
    usuario: Optional[str] = None
    creado_en: datetime.datetime
