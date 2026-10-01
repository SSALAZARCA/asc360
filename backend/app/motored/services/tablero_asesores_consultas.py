"""
Tablero de asesores (feature motored-tablero-asesores, T4): consultas SQL.

Todo se calcula con GROUP BY en PostgreSQL: con ~1M de lineas en 6 meses nunca
se cargan lineas en Python, solo las filas ya agregadas (un cubo por fila del
tablero, mes, linea y banderas, mas facturas y clientes). El reparto en filas y
los indicadores viven en `tablero_asesores.py` (puro, sin base).

Reglas que comparten TODAS las consultas (`_desde_ventas`):
- Solo cargas VENTAS no ANULADAS (anular nunca borra el detalle).
- `fecha` dentro de [inicio, fin) y el filtro HMCL (`incluir`/`excluir`/`solo`).
- Venta de una linea = `valor_bruto - valor_descuentos`.
- Linea = `referencia.linea_comercial` (recortada, mayusculas, sin tildes).
- Cliente normalizado con la MISMA regla que `normalizar_nit` (ver
  `_expr_cliente_norm`), para cruzar con HMCL y con la lista Tecnired.
- Fila del tablero (`_expr_clave`): una persona por asesor de repuestos, un
  grupo para asesores comerciales, otro para otros cargos y "resto" para quien
  no esta (activo) en el maestro. El mapa cargo -> grupo es
  `tablero_asesores.GRUPO_POR_CARGO`.

Costo unitario por referencia: MEDIANA de los costos > 0 de las lineas de
`inventario_detalle` del ultimo `fecha_corte` con carga no ANULADA
(`percentile_cont(0.5)`, la misma mediana de la hoja COSTO REFERENCIA del
Excel). Es especifico de PostgreSQL: la suite prueba estas consultas solo con
`pg_real` (los dobles de sesion no ejecutan SQL), asi que no hay respaldo
portable.
"""
import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import Numeric, String, case, cast, false, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.cliente_tecnired import ClienteTecnired
from app.motored.models.inventario_detalle import InventarioDetalle
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.vendedor import Vendedor
from app.motored.models.venta_detalle import VentaDetalle
from app.motored.services import tablero_asesores as t
from app.motored.services.tablero_asesores import (
    CLAVE_TOTAL, FilaClientes, FilaCubo, FilaFacturas, FilaPersona,
)

TOP_CLIENTES = 5


def _constante(texto: str):
    """Texto fijo como literal SQL (no parametro): asi la misma expresion en el
    SELECT y en el GROUP BY es identica para PostgreSQL. Solo valores propios
    del codigo (constantes), nunca datos del usuario."""
    assert "'" not in texto
    return literal_column(f"'{texto}'")


# --- Expresiones ----------------------------------------------------------------------------


def _expr_clave():
    """Fila del tablero a la que pertenece cada linea de venta."""
    ramas = []
    personas = [c for c, g in t.GRUPO_POR_CARGO.items() if g == t.TIPO_PERSONA]
    ramas.append((Vendedor.id.is_(None), _constante(t.GRUPO_RESTO)))
    ramas.append((Vendedor.cargo.in_(personas), _constante(t.PREFIJO_PERSONA).concat(cast(Vendedor.id, String))))
    for grupo in sorted(set(t.GRUPO_POR_CARGO.values()) - {t.TIPO_PERSONA}):
        cargos = [c for c, g in t.GRUPO_POR_CARGO.items() if g == grupo]
        ramas.append((Vendedor.cargo.in_(cargos), _constante(grupo)))
    return case(*ramas, else_=_constante(t.GRUPO_OTROS))


def _expr_cliente_norm():
    """Misma regla que `schemas.cliente_tecnired.normalizar_nit`: sin espacios,
    sin puntos finales y sin el `.0` de un entero leido como decimal. (Quitar
    los puntos finales primero y luego el `.0+` da el mismo punto fijo que el
    bucle de Python; `pg_real` lo compara con la funcion real.)"""
    sin_espacios = func.regexp_replace(VentaDetalle.cliente_factura, r"\s+", "", "g")
    sin_puntos = func.regexp_replace(sin_espacios, r"\.+$", "")
    return case(
        (sin_puntos.op("~")(r"^\d+\.0+$"), func.regexp_replace(sin_puntos, r"\.0+$", "")),
        else_=sin_puntos,
    )


def _lineas_por_referencia():
    """CTE `(id, linea)` por referencia: la linea comercial normalizada
    (recortada, mayusculas, sin tildes) si es una de las 7, y NULL en cualquier
    otro caso. Se calcula UNA vez por referencia (miles) y no por cada linea de
    venta (millones); MATERIALIZED evita que PostgreSQL la vuelva a inlinear."""
    normalizada = func.upper(func.translate(
        func.trim(Referencia.linea_comercial), t.TILDES_ORIGEN, t.TILDES_DESTINO))
    return (
        select(
            Referencia.id.label("id"),
            case((normalizada.in_(t.LINEAS), normalizada), else_=None).label("linea"),
        )
        .cte("linea_por_referencia")
        .prefix_with("MATERIALIZED")
    )


def _expr_venta():
    return VentaDetalle.valor_bruto - VentaDetalle.valor_descuentos


def _expr_mes():
    return func.to_char(VentaDetalle.fecha, "YYYY-MM")


def _expr_es_hmcl(cliente_norm):
    """Un cliente NULL cuenta como NO HMCL (`NOT IN` con NULL daria NULL y la
    linea desapareceria del filtro `excluir`)."""
    return func.coalesce(cliente_norm.in_(t.HMCL_NITS), false())


def _expr_es_mostrador():
    return func.upper(func.trim(VentaDetalle.origen)) == "MOSTRADOR"


def _subconsulta_costos(fecha_corte: Optional[datetime.date]):
    """Costo unitario por referencia: mediana de los costos positivos."""
    mediana = func.percentile_cont(0.5).within_group(InventarioDetalle.costo_unitario)
    return (
        select(
            InventarioDetalle.referencia_id.label("referencia_id"),
            cast(mediana, Numeric(18, 4)).label("costo_unitario"),
        )
        .join(CargaArchivo, CargaArchivo.id == InventarioDetalle.carga_id)
        .where(
            InventarioDetalle.fecha_corte == fecha_corte,
            InventarioDetalle.costo_unitario > 0,
            CargaArchivo.estado != "ANULADO",
        )
        .group_by(InventarioDetalle.referencia_id)
        .subquery("costos")
    )


def _desde_ventas(consulta, inicio, fin, modo_hmcl, lineas, *, solo_lineas_reconocidas, costos=None):
    """FROM/JOIN/WHERE comunes de todas las consultas del tablero."""
    consulta = (
        consulta.select_from(VentaDetalle)
        .join(CargaArchivo, CargaArchivo.id == VentaDetalle.carga_id)
        .join(lineas, lineas.c.id == VentaDetalle.referencia_id)
        .outerjoin(Vendedor, (Vendedor.nombre_norm == VentaDetalle.vendedor_norm) & Vendedor.activo.is_(True))
    )
    if costos is not None:
        consulta = consulta.outerjoin(costos, costos.c.referencia_id == VentaDetalle.referencia_id)
    consulta = consulta.where(
        CargaArchivo.estado != "ANULADO", VentaDetalle.fecha >= inicio, VentaDetalle.fecha < fin)
    if modo_hmcl == t.HMCL_SOLO:
        consulta = consulta.where(_expr_es_hmcl(_expr_cliente_norm()))
    elif modo_hmcl == t.HMCL_EXCLUIR:
        consulta = consulta.where(~_expr_es_hmcl(_expr_cliente_norm()))
    if solo_lineas_reconocidas:
        consulta = consulta.where(lineas.c.linea.is_not(None))
    return consulta


def _clave_de(por_grupo: bool):
    return _expr_clave() if por_grupo else _constante(CLAVE_TOTAL)


# --- Consultas -------------------------------------------------------------------------------


async def fecha_corte_costos(db: AsyncSession) -> Optional[datetime.date]:
    """Ultimo `fecha_corte` de inventario con carga no ANULADA."""
    return (
        await db.execute(
            select(func.max(InventarioDetalle.fecha_corte))
            .join(CargaArchivo, CargaArchivo.id == InventarioDetalle.carga_id)
            .where(CargaArchivo.estado != "ANULADO")
        )
    ).scalar()


async def meses_disponibles(db: AsyncSession) -> List[str]:
    mes = _expr_mes()
    filas = await db.execute(
        select(mes)
        .select_from(VentaDetalle)
        .join(CargaArchivo, CargaArchivo.id == VentaDetalle.carga_id)
        .where(CargaArchivo.estado != "ANULADO")
        .group_by(mes)
        .order_by(mes)
    )
    return [m for (m,) in filas.all()]


async def consultar_cubo(db, inicio, fin, modo_hmcl, fecha_corte) -> List[FilaCubo]:
    costos = _subconsulta_costos(fecha_corte)
    lineas = _lineas_por_referencia()
    cliente = _expr_cliente_norm()
    columnas = [
        _expr_clave().label("clave"),
        _expr_mes().label("mes"),
        lineas.c.linea.label("linea"),
        _expr_es_hmcl(cliente).label("es_hmcl"),
        cliente.in_(select(ClienteTecnired.nit)).label("es_tecnired"),
        _expr_es_mostrador().label("es_mostrador"),
        costos.c.costo_unitario.is_not(None).label("con_costo"),
    ]
    consulta = select(
        *columnas,
        func.sum(_expr_venta()),
        func.sum(VentaDetalle.valor_bruto),
        func.sum(VentaDetalle.valor_descuentos),
        func.sum(VentaDetalle.cantidad),
        func.count(),
        func.coalesce(func.sum(VentaDetalle.cantidad * costos.c.costo_unitario), 0),
    ).group_by(*columnas)
    consulta = _desde_ventas(consulta, inicio, fin, modo_hmcl, lineas, solo_lineas_reconocidas=False, costos=costos)
    return [
        FilaCubo(clave, mes, linea, hmcl, tec, mostr, costo_ok,
                 Decimal(venta), Decimal(bruto), Decimal(desc), Decimal(cant), int(n), Decimal(costo))
        for clave, mes, linea, hmcl, tec, mostr, costo_ok, venta, bruto, desc, cant, n, costo
        in (await db.execute(consulta)).all()
    ]


async def consultar_facturas(db, inicio, fin, modo_hmcl, *, por_grupo: bool) -> List[FilaFacturas]:
    """Una factura = (nro_documento, sucursal) distinta DENTRO de la fila: por
    cada una se marca que lineas trae y cuantas lineas distintas tiene."""
    lineas = _lineas_por_referencia()
    linea = lineas.c.linea
    clave = _clave_de(por_grupo).label("clave")
    marcas = [
        func.max(case((linea == nombre, 1), else_=0)).label(f"l{i}")
        for i, nombre in enumerate(t.LINEAS)
    ]
    por_factura = [VentaDetalle.nro_documento, VentaDetalle.sucursal_id] + ([clave] if por_grupo else [])
    interna = _desde_ventas(
        select(clave, func.count(func.distinct(linea)).label("lineas_distintas"), *marcas)
        .group_by(*por_factura),
        inicio, fin, modo_hmcl, lineas, solo_lineas_reconocidas=True,
    ).subquery("por_factura")
    externa = select(
        interna.c.clave if por_grupo else _constante(CLAVE_TOTAL),
        func.count(),
        func.coalesce(func.sum(case((interna.c.lineas_distintas > 1, 1), else_=0)), 0),
        *[func.coalesce(func.sum(interna.c[f"l{i}"]), 0) for i in range(len(t.LINEAS))],
    )
    if por_grupo:
        externa = externa.group_by(interna.c.clave)
    return [
        FilaFacturas(fila[0], int(fila[1]), int(fila[2]), tuple(int(n) for n in fila[3:]))
        for fila in (await db.execute(externa)).all()
    ]


async def consultar_clientes(db, inicio, fin, modo_hmcl, *, por_grupo: bool) -> List[FilaClientes]:
    """Clientes distintos y venta de los 5 mayores, por fila."""
    lineas = _lineas_por_referencia()
    cliente = _expr_cliente_norm().label("cliente")
    clave = _clave_de(por_grupo).label("clave")
    por_cliente = [cliente] + ([clave] if por_grupo else [])
    interna = _desde_ventas(
        select(clave, cliente, func.sum(_expr_venta()).label("venta")).group_by(*por_cliente),
        inicio, fin, modo_hmcl, lineas, solo_lineas_reconocidas=True,
    ).subquery("por_cliente")
    posicion = func.row_number().over(
        partition_by=interna.c.clave if por_grupo else None, order_by=interna.c.venta.desc())
    medio = select(interna.c.clave, interna.c.venta, posicion.label("posicion")).subquery("ordenados")
    externa = select(
        medio.c.clave if por_grupo else _constante(CLAVE_TOTAL),
        func.count(),
        func.coalesce(func.sum(case((medio.c.posicion <= TOP_CLIENTES, medio.c.venta), else_=0)), 0),
    )
    if por_grupo:
        externa = externa.group_by(medio.c.clave)
    return [
        FilaClientes(clave_, int(n), Decimal(top5))
        for clave_, n, top5 in (await db.execute(externa)).all()
    ]


async def consultar_personas(db, inicio, fin, modo_hmcl) -> List[FilaPersona]:
    """Quienes hay detras de cada fila: cuantos vendedores distintos y, para una
    persona, su nombre, cargo y punto de venta (sucursal principal)."""
    lineas = _lineas_por_referencia()
    clave = _expr_clave().label("clave")
    consulta = _desde_ventas(
        select(
            clave,
            func.count(func.distinct(VentaDetalle.vendedor_norm)),
            func.min(Vendedor.nombre),
            func.min(Vendedor.cargo),
            func.min(Sucursal.nombre),
        ).group_by(clave),
        inicio, fin, modo_hmcl, lineas, solo_lineas_reconocidas=True,
    ).outerjoin(Sucursal, Sucursal.id == Vendedor.sucursal_id)
    return [FilaPersona(*fila) for fila in (await db.execute(consulta)).all()]


async def calcular_tablero(db: AsyncSession, desde: str, hasta: str, modo_hmcl: str) -> Dict[str, Any]:
    """Tablero completo del rango `desde`..`hasta` (AAAA-MM). Lanza
    `ValueError` si el rango no es valido."""
    meses = t.validar_rango(desde, hasta)
    inicio, fin = t.limites_de_fecha(desde, hasta)
    corte = await fecha_corte_costos(db)

    cubo = await consultar_cubo(db, inicio, fin, modo_hmcl, corte)
    facturas = (await consultar_facturas(db, inicio, fin, modo_hmcl, por_grupo=True)
                + await consultar_facturas(db, inicio, fin, modo_hmcl, por_grupo=False))
    clientes = (await consultar_clientes(db, inicio, fin, modo_hmcl, por_grupo=True)
                + await consultar_clientes(db, inicio, fin, modo_hmcl, por_grupo=False))
    personas = await consultar_personas(db, inicio, fin, modo_hmcl)

    tablero = t.construir_tablero(cubo, facturas, clientes, personas, meses)
    tablero.update(
        desde=desde,
        hasta=hasta,
        hmcl=modo_hmcl,
        meses=meses,
        meses_disponibles=await meses_disponibles(db),
        fecha_corte_costos=corte.isoformat() if corte else None,
    )
    return tablero
