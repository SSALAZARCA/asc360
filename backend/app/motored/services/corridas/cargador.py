"""
Motored Pedidos F3 "Motor" (sdd/motored-pedidos-motor, S5b, ADR-6, decisiones
#1, #4, #6d, #10, #13, #15): cargador de los insumos del motor por sucursal.

Cinco consultas set-based por sucursal (nunca una por referencia; el universo
ronda las 11.700 referencias) y un armado puro de `EntradaReferencia`:

1. ventas por mes, MOSTRADOR + TALLER sumados, en un pivote `FILTER`;
2. demanda perdida por mes de OCURRENCIA (`fecha`), BOT + EXCEL sumados;
3. inventario de la sucursal en el corte de inventario del preflight (V; F2
   ya consolidó las bodegas secundarias en su principal al ingestar);
4. backorder de la sucursal en su corte del preflight (X);
5. atributos de las referencias del universo.

W (tránsito al corte) llega ya calculado y llaveado por sucursal desde
`transito_corte`.

Grupo (sucursales asociadas, `sucursal.principal_id`): sólo la tienda
principal tiene pedido, y sus cinco fuentes (ventas, demanda perdida,
inventario, backorder y W) suman el GRUPO congelado en la corrida
(`seleccion_datos["grupos"]`): la principal más sus asociadas, activas o
no, con toda su historia. Los atributos, días, tope y SIC siguen siendo los
de la principal. Una corrida sin grupo congelado (anterior a la asociación)
lee cada sucursal sola. Toda lectura se limita al proveedor principal (HMCL) y
descarta las filas de cargas EXCEL en estado ANULADO (F2 no las borra al
anular); las filas BOT de demanda perdida quedan exentas, porque su anulación
ya revierte el monto en su lugar.

Universo: referencias con venta > 0 en al menos uno de los seis meses
cerrados. El mes en curso (M0) nunca cuenta; sólo se carga cuando el preflight
lo dejó efectivo (PONDERADO). Con `consolidar_sustituidas` ON se cargan
además las referencias viejas de las cadenas que tengan cualquier dato y sus
sustitutas finales (con ceros si no tienen nada): es el contrato de S3.

Nadie llama a este módulo todavía: lo conecta la corrida (S6a).
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, Iterable, Mapping, Optional, Set, Tuple
from uuid import UUID

from sqlalchemy import and_, func, or_, select, tuple_

from app.motored.models.backorder_linea import BackorderLinea
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.demanda_perdida import DemandaPerdida
from app.motored.models.inventario_snapshot import InventarioSnapshot
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.venta_mensual import VentaMensual
from app.motored.services.corridas import codigos
from app.motored.services.corridas.parametros_corrida import (
    ParametrosCorrida)
from app.motored.services.corridas.transito_corte import (
    ClaveW, TransitoAlCorte)
from app.motored.services.corridas.vigencia import (
    ResultadoVigencia, meses_cerrados)
from app.motored.services.motor.sustitucion import resolver_cadenas
from app.motored.services.motor.tipos import (
    Advertencia,
    AtributosSucursal,
    EntradaReferencia,
    MesEnCurso,
    NodoMaestro,
    Resolucion,
)

ESTADO_ANULADO = "ANULADO"
ORIGEN_BOT = "BOT"
ORIGENES_VENTA = ("MOSTRADOR", "TALLER")
BANDERA_SIN_PRECIO = "SIN_PRECIO"
BANDERA_EMPAQUE_CORREGIDO = "EMPAQUE_CORREGIDO"
DIAS_SEGURIDAD_POR_DEFECTO = Decimal("2.5")

_CERO = Decimal(0)
_CEROS = (_CERO,) * 6
_POSICIONES = range(1, 7)  # c1 = M6 (el más viejo) .. c6 = M1


@dataclass(frozen=True)
class FilaProveedor:
    """El proveedor principal (HMCL) y sus valores por defecto."""

    id: UUID
    dias_empaque_default: Optional[int]
    dias_transito_default: Optional[int]
    dias_seguridad_default: Optional[Decimal]


@dataclass(frozen=True)
class FilaSucursal:
    id: UUID
    nombre: str
    sic: Optional[str]
    fecha_apertura: Optional[date]
    dias_empaque: Optional[int]
    dias_transito: Optional[int]
    dias_seguridad: Optional[Decimal]


@dataclass(frozen=True)
class ContextoCarga:
    """Lo que es común a todas las sucursales de UNA corrida.

    `transito` es W por sucursal y referencia; `resoluciones` va vacío con
    `consolidar` OFF (identidad con el motor sin consolidación). `grupos`
    es el congelado de la corrida: principal -> sus asociadas.
    """

    proveedor: FilaProveedor
    fecha_corte: date
    corte_inventario: date
    corte_backorder: date
    mes_en_curso: Optional[MesEnCurso] = None
    transito: Mapping[UUID, Mapping[UUID, Decimal]] = field(
        default_factory=dict)
    dias_entre_pedidos: Mapping[UUID, int] = field(default_factory=dict)
    consolidar: bool = False
    resoluciones: Mapping[UUID, Resolucion] = field(default_factory=dict)
    grupos: Mapping[UUID, Tuple[UUID, ...]] = field(default_factory=dict)

    def miembros(self, sucursal_id: UUID) -> Tuple[UUID, ...]:
        """La sucursal y, si es principal de un grupo, sus asociadas."""
        return (sucursal_id, *self.grupos.get(sucursal_id, ()))


@dataclass(frozen=True)
class EntradasCargadas:
    entradas: Tuple[EntradaReferencia, ...]
    advertencias: Tuple[Advertencia, ...] = ()


@dataclass(frozen=True)
class DatosSucursal:
    atributos: AtributosSucursal
    entradas: Tuple[EntradaReferencia, ...]
    advertencias: Tuple[Advertencia, ...] = ()


class ErrorCargador(Exception):
    """Error de datos de UNA sucursal (queda FALLIDA; no se reintenta)."""

    def __init__(self, codigo: str, mensaje: str):
        self.codigo = codigo
        self.mensaje = mensaje
        super().__init__(mensaje)


def m0_activo(contexto: ContextoCarga) -> bool:
    mes = contexto.mes_en_curso
    return mes is not None and mes.modo == "PONDERADO"


# --- Contexto de la corrida ----------------------------------------------


def indexar_transito(
    w: Mapping[ClaveW, Decimal],
) -> Mapping[UUID, Mapping[UUID, Decimal]]:
    """`{(sucursal, referencia): W}` -> `{sucursal: {referencia: W}}`."""
    por_sucursal = defaultdict(dict)
    for (sucursal_id, referencia_id), cantidad in w.items():
        por_sucursal[sucursal_id][referencia_id] = cantidad
    return dict(por_sucursal)


def grupos_desde_seleccion(
    seleccion: Mapping[str, Any],
) -> Dict[UUID, Tuple[UUID, ...]]:
    """`seleccion_datos["grupos"]` (`{principal: [asociadas]}` en texto)
    como UUID; vacío en una corrida congelada antes de los grupos."""
    grupos = seleccion.get("grupos") or {}
    return {
        UUID(principal): tuple(UUID(miembro) for miembro in miembros)
        for principal, miembros in grupos.items()
    }


def construir_contexto(
    proveedor: FilaProveedor,
    fecha_corte: date,
    vigencia: ResultadoVigencia,
    transito: TransitoAlCorte,
    params: ParametrosCorrida,
    maestro: Mapping[UUID, NodoMaestro],
) -> ContextoCarga:
    """Junta el preflight, W al corte y el maestro congelado de la corrida."""
    cortes = vigencia.seleccion_datos["cortes"]
    consolidar = params.motor.consolidar_sustituidas
    return ContextoCarga(
        proveedor=proveedor,
        fecha_corte=fecha_corte,
        corte_inventario=date.fromisoformat(cortes["inventario"]),
        corte_backorder=date.fromisoformat(cortes["backorder"]),
        mes_en_curso=vigencia.mes_en_curso.mes_en_curso,
        transito=indexar_transito(transito.w),
        dias_entre_pedidos=dict(params.dias_entre_pedidos),
        consolidar=consolidar,
        resoluciones=resolver_cadenas(maestro) if consolidar else {},
    )


# --- Consultas por sucursal ------------------------------------------------


def _mes_siguiente(primero: date) -> date:
    return (primero.replace(day=28) + timedelta(days=4)).replace(day=1)


def _suma(valor, condicion, etiqueta: str):
    return func.sum(valor).filter(condicion).label(etiqueta)


def _consulta_ventas(
    sucursal_ids: Tuple[UUID, ...], ctx: ContextoCarga,
):
    cerrados = meses_cerrados(ctx.fecha_corte)
    primero_m0 = ctx.fecha_corte.replace(day=1)
    anio, mes = VentaMensual.anio, VentaMensual.mes

    def en_mes(primero: date):
        return and_(anio == primero.year, mes == primero.month)

    columnas = [
        _suma(VentaMensual.unidades, en_mes(primero), f"c{posicion}")
        for posicion, primero in zip(_POSICIONES, cerrados)
    ]
    ultimo = cerrados[-1]
    if m0_activo(ctx):
        columnas.append(_suma(VentaMensual.unidades, en_mes(primero_m0), "c0"))
        ultimo = primero_m0
    return (
        select(VentaMensual.referencia_id, *columnas)
        .join(Referencia, Referencia.id == VentaMensual.referencia_id)
        .join(CargaArchivo, CargaArchivo.id == VentaMensual.carga_id)
        .where(
            VentaMensual.sucursal_id.in_(sucursal_ids),
            Referencia.proveedor_id == ctx.proveedor.id,
            CargaArchivo.estado != ESTADO_ANULADO,
            VentaMensual.origen.in_(ORIGENES_VENTA),
            tuple_(anio, mes) >= tuple_(cerrados[0].year, cerrados[0].month),
            tuple_(anio, mes) <= tuple_(ultimo.year, ultimo.month),
        )
        .group_by(VentaMensual.referencia_id)
    )


def _consulta_perdidas(
    sucursal_ids: Tuple[UUID, ...], ctx: ContextoCarga,
):
    cerrados = meses_cerrados(ctx.fecha_corte)
    primero_m0 = ctx.fecha_corte.replace(day=1)
    fecha = DemandaPerdida.fecha
    columnas = [
        _suma(
            DemandaPerdida.cantidad_solicitada,
            and_(fecha >= primero, fecha < _mes_siguiente(primero)),
            f"c{posicion}")
        for posicion, primero in zip(_POSICIONES, cerrados)
    ]
    if m0_activo(ctx):
        columnas.append(_suma(
            DemandaPerdida.cantidad_solicitada,
            and_(fecha >= primero_m0, fecha <= ctx.fecha_corte), "c0"))
        tope = fecha <= ctx.fecha_corte
    else:
        tope = fecha < primero_m0
    return (
        select(DemandaPerdida.referencia_id, *columnas)
        .join(Referencia, Referencia.id == DemandaPerdida.referencia_id)
        .join(CargaArchivo, CargaArchivo.id == DemandaPerdida.carga_id)
        .where(
            DemandaPerdida.sucursal_id.in_(sucursal_ids),
            Referencia.proveedor_id == ctx.proveedor.id,
            fecha >= cerrados[0],
            tope,
            or_(DemandaPerdida.origen == ORIGEN_BOT,
                CargaArchivo.estado != ESTADO_ANULADO),
        )
        .group_by(DemandaPerdida.referencia_id)
    )


def _consulta_inventario(
    sucursal_ids: Tuple[UUID, ...], ctx: ContextoCarga,
):
    return (
        select(
            InventarioSnapshot.referencia_id,
            func.sum(InventarioSnapshot.existencias).label("total"))
        .join(Referencia, Referencia.id == InventarioSnapshot.referencia_id)
        .join(CargaArchivo, CargaArchivo.id == InventarioSnapshot.carga_id)
        .where(
            InventarioSnapshot.sucursal_id.in_(sucursal_ids),
            InventarioSnapshot.fecha_corte == ctx.corte_inventario,
            Referencia.proveedor_id == ctx.proveedor.id,
            CargaArchivo.estado != ESTADO_ANULADO,
        )
        .group_by(InventarioSnapshot.referencia_id)
    )


def _consulta_backorder(
    sucursal_ids: Tuple[UUID, ...], ctx: ContextoCarga,
):
    return (
        select(
            BackorderLinea.referencia_id,
            func.sum(BackorderLinea.cantidad_pendiente).label("total"))
        .join(Referencia, Referencia.id == BackorderLinea.referencia_id)
        .join(CargaArchivo, CargaArchivo.id == BackorderLinea.carga_id)
        .where(
            BackorderLinea.sucursal_id.in_(sucursal_ids),
            BackorderLinea.fecha_corte == ctx.corte_backorder,
            Referencia.proveedor_id == ctx.proveedor.id,
            CargaArchivo.estado != ESTADO_ANULADO,
        )
        .group_by(BackorderLinea.referencia_id)
    )


def _consulta_referencias(ids: Iterable[UUID], proveedor_id: UUID):
    return select(
        Referencia.id, Referencia.codigo, Referencia.nombre,
        Referencia.linea_comercial, Referencia.precio_normal,
        Referencia.unidad_empaque, Referencia.unidad_empaque_advertencia,
    ).where(
        Referencia.id.in_(sorted(ids, key=str)),
        Referencia.proveedor_id == proveedor_id,
    )


# --- Armado puro ------------------------------------------------------------


@dataclass(frozen=True)
class _Serie:
    cerrados: Tuple[Decimal, ...]
    m0: Optional[Decimal]


@dataclass(frozen=True)
class _Insumos:
    """Números crudos de la sucursal, por referencia."""

    ventas: Mapping[UUID, _Serie]
    perdidas: Mapping[UUID, _Serie]
    inventario: Mapping[UUID, Decimal]
    backorder: Mapping[UUID, Decimal]
    transito: Mapping[UUID, Decimal]
    con_m0: bool

    def sin_serie(self) -> _Serie:
        return _Serie(_CEROS, _CERO if self.con_m0 else None)


def _dec(valor) -> Decimal:
    return _CERO if valor is None else Decimal(valor)


def _indexar_series(filas, con_m0: bool) -> dict:
    return {
        fila.referencia_id: _Serie(
            tuple(_dec(getattr(fila, f"c{i}")) for i in _POSICIONES),
            _dec(getattr(fila, "c0", None)) if con_m0 else None)
        for fila in filas
    }


def _indexar_totales(filas) -> dict:
    totales: dict = defaultdict(Decimal)
    for fila in filas:
        totales[fila.referencia_id] += _dec(fila.total)
    return dict(totales)


def _universo(insumos: _Insumos) -> Set[UUID]:
    """Venta > 0 en al menos uno de los seis meses cerrados (M0 no cuenta)."""
    return {
        referencia_id for referencia_id, serie in insumos.ventas.items()
        if any(venta > 0 for venta in serie.cerrados)
    }


def _con_datos(insumos: _Insumos, referencia_id: UUID) -> bool:
    numeros = [
        insumos.inventario.get(referencia_id, _CERO),
        insumos.backorder.get(referencia_id, _CERO),
        insumos.transito.get(referencia_id, _CERO),
    ]
    for serie in (insumos.ventas.get(referencia_id),
                  insumos.perdidas.get(referencia_id)):
        if serie is not None:
            numeros += [*serie.cerrados, serie.m0 or _CERO]
    return any(numero != 0 for numero in numeros)


def seleccionar_ids(insumos: _Insumos, ctx: ContextoCarga) -> Set[UUID]:
    """Referencias a cargar: el universo y, con consolidación ON, las viejas
    de las cadenas con algún dato más sus sustitutas finales."""
    ids = _universo(insumos)
    if not ctx.consolidar:
        return ids
    viejas = {
        referencia_id
        for referencia_id, resolucion in ctx.resoluciones.items()
        if resolucion.motivo is not None
        and _con_datos(insumos, referencia_id)
    }
    finales = {
        ctx.resoluciones[referencia_id].final_id for referencia_id in viejas
        if ctx.resoluciones[referencia_id].final_id is not None
    }
    return ids | viejas | finales


def _banderas(atributos) -> frozenset:
    banderas = set()
    if atributos.precio_normal is None:
        banderas.add(BANDERA_SIN_PRECIO)
    if atributos.unidad_empaque_advertencia:
        banderas.add(BANDERA_EMPAQUE_CORREGIDO)
    return frozenset(banderas)


def _entrada(atributos, insumos: _Insumos) -> EntradaReferencia:
    referencia_id = atributos.id
    venta = insumos.ventas.get(referencia_id) or insumos.sin_serie()
    perdida = insumos.perdidas.get(referencia_id) or insumos.sin_serie()
    return EntradaReferencia(
        referencia_id=referencia_id,
        codigo=atributos.codigo,
        nombre=atributos.nombre,
        linea_comercial=atributos.linea_comercial,
        precio=atributos.precio_normal,
        unidad_empaque=atributos.unidad_empaque,
        ventas=venta.cerrados,
        perdidas=perdida.cerrados,
        venta_m0=venta.m0,
        perdida_m0=perdida.m0,
        inventario=insumos.inventario.get(referencia_id, _CERO),
        transito=insumos.transito.get(referencia_id, _CERO),
        backorder=insumos.backorder.get(referencia_id, _CERO),
        banderas=_banderas(atributos),
    )


def _aviso_sin_precio(entrada: EntradaReferencia) -> Advertencia:
    codigo = codigos.A_CORRIDA_SIN_PRECIO
    return Advertencia(
        codigo, codigos.mensaje(codigo, referencia=entrada.codigo))


def armar_entradas(filas_referencia: Iterable, insumos: _Insumos
                   ) -> EntradasCargadas:
    """Entradas ordenadas por código; un id sin fila de referencia (no es un
    HMCL válido) se omite. Avisa las del universo sin precio."""
    universo = _universo(insumos)
    entradas = sorted(
        (_entrada(fila, insumos) for fila in filas_referencia),
        key=lambda entrada: entrada.codigo)
    avisos = tuple(
        _aviso_sin_precio(entrada) for entrada in entradas
        if BANDERA_SIN_PRECIO in entrada.banderas
        and entrada.referencia_id in universo)
    return EntradasCargadas(tuple(entradas), avisos)


# --- Atributos de la sucursal -------------------------------------------


def _primero(*valores):
    return next((valor for valor in valores if valor is not None), None)


def _dias(valor) -> Decimal:
    return _CERO if valor is None else Decimal(valor)


def resolver_atributos(
    sucursal: FilaSucursal, proveedor: FilaProveedor, fecha_corte: date,
    dias_entre_pedidos: int,
) -> AtributosSucursal:
    """Atributos de la sucursal; E-CORRIDA-021 sin SIC y E-CORRIDA-020 si no
    hay ni días de empaque ni de tránsito (propios ni del proveedor)."""
    nombre = sucursal.nombre.strip()
    if not (sucursal.sic or "").strip():
        raise ErrorCargador(
            codigos.E_CORRIDA_SUCURSAL_SIN_SIC,
            codigos.mensaje(
                codigos.E_CORRIDA_SUCURSAL_SIN_SIC, sucursal=nombre))
    empaque = _primero(sucursal.dias_empaque, proveedor.dias_empaque_default)
    transito = _primero(
        sucursal.dias_transito, proveedor.dias_transito_default)
    if empaque is None and transito is None:
        raise ErrorCargador(
            codigos.E_CORRIDA_SIN_EMPAQUE_NI_TRANSITO,
            codigos.mensaje(
                codigos.E_CORRIDA_SIN_EMPAQUE_NI_TRANSITO, sucursal=nombre))
    seguridad = _primero(
        sucursal.dias_seguridad, proveedor.dias_seguridad_default,
        DIAS_SEGURIDAD_POR_DEFECTO)
    return AtributosSucursal(
        sucursal_id=sucursal.id,
        nombre=nombre,
        fecha_corte=fecha_corte,
        fecha_apertura=sucursal.fecha_apertura,
        dias_empaque=_dias(empaque),
        dias_transito=_dias(transito),
        dias_seguridad=Decimal(seguridad),
        dias_entre_pedidos=Decimal(dias_entre_pedidos),
    )


# --- Lecturas ---------------------------------------------------------


async def cargar_proveedor_principal(db) -> FilaProveedor:
    """El proveedor con `es_principal` (debe ser exactamente uno)."""
    resultado = await db.execute(
        select(
            Proveedor.id, Proveedor.dias_empaque_default,
            Proveedor.dias_transito_default, Proveedor.dias_seguridad_default,
        ).where(Proveedor.es_principal.is_(True)))
    filas = resultado.all()
    if len(filas) != 1:
        raise LookupError(
            f"se esperaba exactamente un proveedor principal, hay "
            f"{len(filas)}")
    fila = filas[0]
    return FilaProveedor(
        fila.id, fila.dias_empaque_default, fila.dias_transito_default,
        fila.dias_seguridad_default)


async def cargar_maestro(
    db, proveedor_id: UUID,
) -> Mapping[UUID, NodoMaestro]:
    """Nodos del maestro de sustitución: las referencias del proveedor que
    están inactivas o declaran `sustituida_por` (el resto son FINALES)."""
    resultado = await db.execute(
        select(Referencia.id, Referencia.activa, Referencia.sustituida_por)
        .where(
            Referencia.proveedor_id == proveedor_id,
            or_(Referencia.sustituida_por.is_not(None),
                Referencia.activa.is_(False))))
    return {
        fila.id: NodoMaestro(fila.id, fila.activa, fila.sustituida_por)
        for fila in resultado.all()
    }


async def cargar_sucursal_fila(db, sucursal_id: UUID) -> FilaSucursal:
    resultado = await db.execute(
        select(
            Sucursal.id, Sucursal.nombre, Sucursal.sic,
            Sucursal.fecha_apertura, Sucursal.dias_empaque,
            Sucursal.dias_transito, Sucursal.dias_seguridad,
        ).where(Sucursal.id == sucursal_id))
    fila = resultado.first()
    if fila is None:
        raise LookupError(f"la sucursal {sucursal_id} no existe")
    return FilaSucursal(
        fila.id, fila.nombre, fila.sic, fila.fecha_apertura,
        fila.dias_empaque, fila.dias_transito, fila.dias_seguridad)


def _transito_grupo(
    ctx: ContextoCarga, miembros: Tuple[UUID, ...],
) -> Mapping[UUID, Decimal]:
    """W del grupo: el de cada miembro, sumado por referencia."""
    if len(miembros) == 1:
        return ctx.transito.get(miembros[0], {})
    total: Dict[UUID, Decimal] = defaultdict(Decimal)
    for miembro in miembros:
        for referencia_id, cantidad in ctx.transito.get(miembro, {}).items():
            total[referencia_id] += cantidad
    return dict(total)


async def cargar_entradas(
    db, sucursal_id: UUID, ctx: ContextoCarga,
) -> EntradasCargadas:
    """Las cinco consultas del grupo de la sucursal (ella sola si no es
    principal de nadie) y el armado de sus entradas. Cada consulta agrupa
    por referencia, así que suma los miembros."""
    miembros = ctx.miembros(sucursal_id)
    ventas = await db.execute(_consulta_ventas(miembros, ctx))
    perdidas = await db.execute(_consulta_perdidas(miembros, ctx))
    inventario = await db.execute(_consulta_inventario(miembros, ctx))
    backorder = await db.execute(_consulta_backorder(miembros, ctx))
    con_m0 = m0_activo(ctx)
    insumos = _Insumos(
        ventas=_indexar_series(ventas.all(), con_m0),
        perdidas=_indexar_series(perdidas.all(), con_m0),
        inventario=_indexar_totales(inventario.all()),
        backorder=_indexar_totales(backorder.all()),
        transito=_transito_grupo(ctx, miembros),
        con_m0=con_m0,
    )
    ids = seleccionar_ids(insumos, ctx)
    if not ids:
        return EntradasCargadas(())
    referencias = await db.execute(
        _consulta_referencias(ids, ctx.proveedor.id))
    return armar_entradas(referencias.all(), insumos)


async def cargar_sucursal(
    db, sucursal_id: UUID, ctx: ContextoCarga,
) -> DatosSucursal:
    """Atributos y entradas de una sucursal, listos para el motor.

    Falla con `ErrorCargador` (E-CORRIDA-020/021) antes de leer movimientos.
    """
    fila = await cargar_sucursal_fila(db, sucursal_id)
    atributos = resolver_atributos(
        fila, ctx.proveedor, ctx.fecha_corte,
        ctx.dias_entre_pedidos[sucursal_id])
    cargadas = await cargar_entradas(db, sucursal_id, ctx)
    return DatosSucursal(
        atributos, cargadas.entradas, cargadas.advertencias)
