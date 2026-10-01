"""
Motored Pedidos F4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B2, B3a,
B3b, ADR-1, ADR-3): esquemas de la edición de líneas y su historial y del
ciclo de vida del pedido por tienda (cerrar, reabrir, enviar, corregir el
número de orden, cabecera y eventos).

`pedido_final` entra SIN tipo (`Any`): la regla de E-CORRIDA-053 la aplica el
servicio, DESPUÉS de los chequeos de estado (404, 042, 065, 052), así un valor
inválido siempre responde con su código y no con el 422 genérico del
validador. Los campos extra se prohíben (no se acepta Z ni nada más). Igual
el `motivo` de reabrir (E-CORRIDA-046) y el número y la fecha de un envío
(E-CORRIDA-048).
"""
import datetime
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.motored.schemas.corrida import (
    AccionesTienda,
    EnvioInfo,
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


class EnviarCuerpo(BaseModel):
    """Cuerpo de `POST .../sucursales/{sid}/enviar`: el número de orden del
    proveedor (1..50) y la fecha de envío; sin tipo, el servicio los valida
    (048) después de los chequeos de estado."""

    model_config = ConfigDict(extra="forbid")

    numero_pedido_proveedor: Any = None
    fecha_envio: Any = None


class EnvioItem(EnviarCuerpo):
    """Una tienda de `POST /corridas/{id}/enviar`, con su propio número."""

    sucursal_id: uuid.UUID


class EnviarLote(BaseModel):
    """Cuerpo de `POST /corridas/{id}/enviar`: de 1 a 200 tiendas, todo o
    nada."""

    model_config = ConfigDict(extra="forbid")

    envios: List[EnvioItem] = Field(..., min_length=1, max_length=200)


class CorregirEnvio(BaseModel):
    """Cuerpo de `PATCH .../sucursales/{sid}/envio`: sólo el número de orden
    se corrige (F4-15); la fecha de envío no."""

    model_config = ConfigDict(extra="forbid")

    numero_pedido_proveedor: Any = None


class EnvioTienda(BaseModel):
    """El envío de UNA tienda: su número de orden, fecha, quién y cuándo."""

    corrida_id: uuid.UUID
    sucursal_id: uuid.UUID
    estado_pedido: str = "ENVIADO"
    numero_pedido_proveedor: str
    fecha_envio: datetime.date
    enviada_por: uuid.UUID
    enviada_en: datetime.datetime


class EnvioLote(BaseModel):
    """Respuesta del envío por lote: la corrida (su `estado` es el del
    cálculo) y los envíos que quedaron escritos."""

    id: uuid.UUID
    codigo: str
    estado: str
    enviadas: List[EnvioTienda]


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
    envio: Optional[EnvioInfo] = None


class EventoPedido(BaseModel):
    """Una fila de la línea de tiempo del pedido de una tienda."""

    id: int
    evento: str
    motivo: Optional[str] = None
    detalle: Optional[Dict[str, Any]] = None
    usuario_id: Optional[uuid.UUID] = None
    usuario: Optional[str] = None
    creado_en: datetime.datetime


# --- Tope de presupuesto por tienda (B5a, F4-7) ------------------------------


class TopeCuerpo(BaseModel):
    """Una entrada de `POST /parametros/topes-presupuesto`. `valor` es
    obligatorio y sin tipo: un número positivo fija el tope, `null` lo quita,
    y cualquier otra cosa es E-PARAM-002 (la regla la aplica el servicio)."""

    model_config = ConfigDict(extra="forbid")

    sucursal_id: uuid.UUID
    valor: Any


class TopesGuardar(BaseModel):
    """Cuerpo de `POST /parametros/topes-presupuesto` (1 a 200 entradas;
    el largo lo valida el servicio para responder con su código)."""

    model_config = ConfigDict(extra="forbid")

    topes: List[TopeCuerpo]


class TopeTienda(BaseModel):
    """El tope vigente de una tienda; `valor` nulo = sin tope."""

    sucursal_id: uuid.UUID
    nombre: str
    valor: Optional[Decimal] = None
    vigente_desde: Optional[datetime.date] = None


class TopesPresupuesto(BaseModel):
    """El interruptor global y el tope de cada tienda activa."""

    modo_activo: bool
    modo_vigente_desde: Optional[datetime.date] = None
    topes: List[TopeTienda]


class TopesGuardados(BaseModel):
    """Qué tiendas recibieron una versión nueva y cuáles ya tenían ese
    valor."""

    actualizados: List[uuid.UUID]
    sin_cambios: List[uuid.UUID]
