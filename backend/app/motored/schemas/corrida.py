"""
Motored Pedidos F3 "Motor" (sdd/motored-pedidos-motor, S7, ADR-9): esquemas
de la API `/api/motored/corridas`.

Los decimales se serializan como texto exacto (`"50.00"`), nunca como float:
ni el pedido ni el valor pasan por coma flotante en el camino a la pantalla.
Ningún esquema de escritura acepta `pedido_final` ni el ajuste Z (no se
editan en F3): el cuerpo del POST prohíbe campos extra.
"""
import datetime
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing_extensions import Annotated

Nota = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=500)]
Motivo = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1,
                           max_length=500)]
Dec = Optional[Decimal]


# --- Escritura --------------------------------------------------------------


class CorridaCreate(BaseModel):
    """Cuerpo de `POST /corridas`. `sucursal_ids` omitido = todas las
    sucursales activas. `nota` no tiene columna: queda en el evento CREADA
    del log de la corrida."""

    model_config = ConfigDict(extra="forbid")

    fecha_corte: datetime.date
    sucursal_ids: Optional[List[uuid.UUID]] = Field(None, min_length=1)
    overrides: Optional[Dict[str, Any]] = None
    nota: Optional[Nota] = None


class CorridaCreada(BaseModel):
    id: uuid.UUID
    codigo: str
    estado: str
    es_escenario: bool


class CorridaAnular(BaseModel):
    model_config = ConfigDict(extra="forbid")

    motivo: Motivo


class CorridaEstado(BaseModel):
    """Respuesta de cerrar y anular."""

    id: uuid.UUID
    codigo: str
    estado: str


# --- Lista y detalle --------------------------------------------------------


class CorridaItem(BaseModel):
    id: uuid.UUID
    codigo: str
    proveedor_id: uuid.UUID
    fecha_corte: datetime.date
    estado: str
    es_escenario: bool
    alcance: str
    invalidada: bool
    sucursales_total: int
    sucursales_procesadas: int
    nota: Optional[str] = None
    created_at: Optional[datetime.datetime] = None
    terminado_en: Optional[datetime.datetime] = None
    cerrada_en: Optional[datetime.datetime] = None


class PaginaCorridas(BaseModel):
    items: List[CorridaItem]
    total: int
    limite: int
    offset: int


class CargaUsada(BaseModel):
    carga_id: uuid.UUID
    nombre_archivo: Optional[str] = None
    estado: str
    periodo_desde: Optional[datetime.date] = None
    periodo_hasta: Optional[datetime.date] = None


class Aviso(BaseModel):
    """Aviso o error; `sucursal_id` vacío = de la corrida entera."""

    sucursal_id: Optional[uuid.UUID] = None
    sucursal: Optional[str] = None
    codigo: Optional[str] = None
    mensaje: Optional[str] = None


class SucursalEstado(BaseModel):
    sucursal_id: uuid.UUID
    nombre: str
    orden: int
    estado: str
    codigo: Optional[str] = None
    mensaje: Optional[str] = None
    lineas: int
    excluidas: int
    unidades: Dec = None
    valor: Dec = None
    fecha_apertura: Optional[datetime.date] = None
    divisor: Optional[int] = None
    dias_empaque: Dec = None
    dias_transito: Dec = None
    dias_seguridad: Dec = None
    dias_entre_pedidos: Dec = None
    intentos: int


class ResumenClase(BaseModel):
    """Una clase (AF..DS o TOTAL); `sucursal_id` vacío = suma de las
    sucursales visibles."""

    sucursal_id: Optional[uuid.UUID] = None
    clase: str
    unidades: Decimal
    referencias: int
    valor: Decimal
    porcentaje_peso: Dec = None


class Totales(BaseModel):
    unidades: Decimal
    referencias: int
    valor: Decimal


class CorridaDetalle(CorridaItem):
    """La corrida con sus insumos congelados. `antiguedad` (decisión #16)
    trae, por tipo de dato, la fecha usada, su antigüedad y el límite
    aplicado con su fuente."""

    parametros_en_fecha: Optional[datetime.date] = None
    overrides: Optional[Dict[str, Any]] = None
    motivo_invalidacion: Optional[Dict[str, Any]] = None
    motivo_anulacion: Optional[str] = None
    iniciado_en: Optional[datetime.datetime] = None
    anulada_en: Optional[datetime.datetime] = None
    intentos: int
    cargas_usadas: Dict[str, List[CargaUsada]]
    parametros: Dict[str, Any]
    antiguedad: Dict[str, Any]
    mes_en_curso: Optional[Dict[str, Any]] = None
    advertencias: List[Aviso]
    sucursales: List[SucursalEstado]
    resumen: List[ResumenClase]
    resumen_por_clase: List[ResumenClase]
    totales: Totales
    # Fase 4 (B2): lo que se va a PEDIR (`pedido_final`), junto a las cifras
    # del sugerido (`resumen`, `totales`), que no cambian al editar.
    resumen_a_pedir: List[ResumenClase] = Field(default_factory=list)
    totales_a_pedir: Optional[Totales] = None


class Progreso(BaseModel):
    estado: str
    total: int
    procesadas: int
    ok: int
    omitidas: int
    fallidas: int
    actual: Optional[str] = None
    latido_en: Optional[datetime.datetime] = None
    intentos: int
    errores: List[Aviso]
    advertencias: List[Aviso]


# --- Líneas -----------------------------------------------------------------


class LineaRead(BaseModel):
    """Una línea de la corrida: entradas crudas propias y salidas del motor.
    `pedido_final` parte igual a `pedido_sugerido` y lo edita el comprador
    (F4); `valor_sugerido`, `fuera_de_empaque` y las marcas de edición se
    calculan al leer (`proyecciones.extras_linea`)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    sucursal_id: uuid.UUID
    referencia_id: uuid.UUID
    codigo_referencia: str
    nombre_parte: Optional[str] = None
    linea_comercial: Optional[str] = None
    # Entradas: ventas y pérdidas de los seis meses cerrados (m6 el más
    # antiguo), mes en curso (sólo con modo PONDERADO), T, U, V, W, X, Z.
    venta_m6: Decimal
    venta_m5: Decimal
    venta_m4: Decimal
    venta_m3: Decimal
    venta_m2: Decimal
    venta_m1: Decimal
    perdida_m6: Decimal
    perdida_m5: Decimal
    perdida_m4: Decimal
    perdida_m3: Decimal
    perdida_m2: Decimal
    perdida_m1: Decimal
    venta_m0: Dec = None
    perdida_m0: Dec = None
    precio: Dec = None
    unidad_empaque: int
    inventario: Decimal
    transito: Decimal
    backorder: Decimal
    ajuste: Decimal
    # Salidas.
    demanda_perdida: Dec = None
    demanda_perdida_mensualizada: Dec = None
    demanda_prom_simple: Dec = None
    venta_m0_proyectada: Dec = None
    demanda_ponderada: Dec = None
    peso_pct: Dec = None
    peso_acum_pct: Dec = None
    orden_abc: Optional[int] = None
    clase_abc: Optional[str] = None
    clase_fms: Optional[str] = None
    clase: Optional[str] = None
    meses_con_venta: Optional[int] = None
    meses_cobertura: Dec = None
    inventario_final: Dec = None
    y_recibido: Dec = None
    stock_objetivo: Dec = None
    pedido_sugerido: Dec = None
    pedido_final: Dec = None
    valor_pedido: Dec = None
    cobertura_final: Dec = None
    cobertura_actual: Dec = None
    punto_minimo: Dec = None
    punto_maximo: Dec = None
    estado_quiebre: Optional[str] = None
    motivo_exclusion: Optional[str] = None
    sustituta_final_id: Optional[uuid.UUID] = None
    banderas: List[str] = Field(default_factory=list)
    detalle_consolidacion: Optional[Dict[str, Any]] = None
    # Fase 4: lo que agrega la edición (no son columnas de la línea).
    valor_sugerido: Dec = None
    fuera_de_empaque: bool = False
    editada: bool = False
    editado_por: Optional[str] = None
    editado_en: Optional[datetime.datetime] = None
    motivo_edicion: Optional[str] = None


class PaginaLineas(BaseModel):
    items: List[LineaRead]
    total: int
    limite: int
    offset: int
