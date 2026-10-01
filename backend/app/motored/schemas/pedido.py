"""
Motored Pedidos F4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B2, B3a,
B3b, ADR-1, ADR-3): esquemas de la edición de líneas y su historial y del
ciclo de vida del pedido por tienda (cerrar, reabrir, enviar, corregir el
número de orden, cabecera y eventos), del recorte al tope de presupuesto
(B5b) y de las vistas de la red (B6): el consolidado, la comparación de un
escenario y el catálogo de claves del motor.

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


# --- Recorte al tope de presupuesto (B5b, F4-7) ------------------------------


class RecorteCuerpo(BaseModel):
    """Cuerpo de `POST .../sucursales/{sid}/recorte`: el `token` de la
    propuesta que el usuario vio. Sin tipo, el servicio lo compara (un token
    que falta o no es texto es E-CORRIDA-060, no el 422 del validador)."""

    model_config = ConfigDict(extra="forbid")

    token: Any = None


class Advertencia(BaseModel):
    """Un aviso con su código (A-CORRIDA-120 o 121) y su texto."""

    codigo: str
    mensaje: str


class RecorteLinea(BaseModel):
    """Lo que se le quita a UNA línea: de `pedido_actual` a
    `pedido_propuesto`, en empaques y en valor."""

    linea_id: int
    codigo: str
    nombre: Optional[str] = None
    clase_abc: str
    unidad_empaque: int
    pedido_actual: Decimal
    pedido_propuesto: Decimal
    empaques_recortados: Optional[Decimal] = None
    valor_recortado: Decimal


class PropuestaRecorteTienda(BaseModel):
    """La propuesta de recorte de una tienda. Con `activo` falso no hay
    propuesta: `motivo_inactivo` dice por qué (MODO_OFF, SIN_TOPE,
    NO_BORRADOR, ESCENARIO, SIN_PEDIDO, CORRIDA_NO_CALCULADA o
    CORRIDA_INVALIDADA) y `modo_activo` sólo se conoce si se llegó a leer."""

    activo: bool
    motivo_inactivo: Optional[str] = None
    modo_activo: Optional[bool] = None
    corrida_id: uuid.UUID
    sucursal_id: uuid.UUID
    tope: Optional[Decimal] = None
    valor_actual: Optional[Decimal] = None
    exceso: Optional[Decimal] = None
    recortes: List[RecorteLinea] = Field(default_factory=list)
    valor_final: Optional[Decimal] = None
    exceso_residual: Optional[Decimal] = None
    lineas_sin_precio: int = 0
    advertencias: List[Advertencia] = Field(default_factory=list)
    token: Optional[str] = None


class RecorteAplicado(BaseModel):
    """Respuesta de aplicar el recorte: lo liberado, lo que queda y los
    totales nuevos de la tienda."""

    corrida_id: uuid.UUID
    sucursal_id: uuid.UUID
    tope: Decimal
    lineas_recortadas: int
    valor_liberado: Decimal
    valor_final: Decimal
    exceso_residual: Decimal
    advertencias: List[Advertencia] = Field(default_factory=list)
    totales_tienda: TotalesTienda


class TopeTiendaCorrida(BaseModel):
    """Una tienda con pedido en el resumen de topes de una corrida; sin tope
    propio, `tope` y `exceso` van nulos."""

    sucursal_id: uuid.UUID
    nombre: str
    estado_pedido: str
    tope: Optional[Decimal] = None
    valor_a_pedir: Decimal
    exceso: Optional[Decimal] = None
    lineas_sin_precio: int


class TopesCorrida(BaseModel):
    """El resumen de topes de una corrida; `activo` falso (modo apagado,
    escenario o sin calcular) no trae tiendas."""

    activo: bool
    corrida_id: uuid.UUID
    tiendas: List[TopeTiendaCorrida] = Field(default_factory=list)


# --- Vistas de la red: consolidado y comparación (B6) -----------------------


class TiendaConsolidado(BaseModel):
    """Una columna de la matriz: la tienda con el estado de su cálculo y de
    su pedido y lo que se pide en ella (TODAS sus referencias, no sólo la
    página). Una tienda fallida u omitida va marcada (`estado`, `codigo`,
    `mensaje`) y sin números."""

    sucursal_id: uuid.UUID
    nombre: str
    estado: str
    estado_pedido: Optional[str] = None
    codigo: Optional[str] = None
    mensaje: Optional[str] = None
    unidades: Optional[Decimal] = None
    valor: Optional[Decimal] = None


class FilaConsolidado(BaseModel):
    """Una referencia: su total sobre las tiendas de la matriz y sus celdas
    (la cantidad a pedir por el id de cada tienda que pide algo)."""

    referencia_id: uuid.UUID
    codigo: str
    nombre: Optional[str] = None
    total: Decimal
    celdas: Dict[str, Decimal] = Field(default_factory=dict)


class TotalesConsolidado(BaseModel):
    """Lo que se pide en toda la red: la suma de las columnas."""

    unidades: Decimal
    valor: Decimal


class ConsolidadoRead(BaseModel):
    """La matriz consolidada de una corrida; `total` cuenta las referencias
    (paginadas por `limite` y `offset`)."""

    corrida_id: uuid.UUID
    codigo: str
    estado: str
    es_escenario: bool
    tiendas: List[TiendaConsolidado] = Field(default_factory=list)
    filas: List[FilaConsolidado] = Field(default_factory=list)
    totales: TotalesConsolidado
    total: int
    limite: int
    offset: int


class CorridaComparada(BaseModel):
    """Una de las dos corridas de la comparación."""

    id: uuid.UUID
    codigo: str
    estado: str
    es_escenario: bool


class FilaComparacion(BaseModel):
    """Una (tienda, referencia): lo sugerido en la corrida real y en el
    escenario y su delta (escenario - real); lo que falta de un lado vale 0.
    `pedido_final_real` es sólo contexto."""

    sucursal_id: uuid.UUID
    sucursal: str
    referencia_id: uuid.UUID
    codigo: str
    nombre: Optional[str] = None
    clase_real: Optional[str] = None
    clase_prueba: Optional[str] = None
    sugerido_real: Decimal
    sugerido_prueba: Decimal
    delta: Decimal
    pedido_final_real: Decimal


class TotalComparacion(BaseModel):
    """Lo sugerido en una tienda, en unidades y en valor, de cada lado."""

    sucursal_id: uuid.UUID
    nombre: str
    unidades_real: Decimal
    unidades_prueba: Decimal
    diferencia_unidades: Decimal
    valor_real: Decimal
    valor_prueba: Decimal
    diferencia_valor: Decimal


class NoComparable(BaseModel):
    """Una tienda que no se compara, con su estado de cada lado (nulo si no
    está en esa corrida) y el motivo."""

    sucursal_id: uuid.UUID
    nombre: str
    estado_real: Optional[str] = None
    estado_prueba: Optional[str] = None
    motivo: str


class ComparacionRead(BaseModel):
    """El escenario frente a su corrida real, paginado por filas."""

    escenario: CorridaComparada
    real: CorridaComparada
    fecha_corte: datetime.date
    filas: List[FilaComparacion] = Field(default_factory=list)
    total: int
    limite: int
    offset: int
    totales_por_sucursal: List[TotalComparacion] = Field(
        default_factory=list)
    no_comparables: List[NoComparable] = Field(default_factory=list)


class ClaveCatalogo(BaseModel):
    """Una clave del motor para el lanzador de escenarios (`opciones` sólo
    en las de tipo opción)."""

    clave: str
    tipo: str
    dominio: str
    default: Any = None
    opciones: Optional[List[str]] = None
