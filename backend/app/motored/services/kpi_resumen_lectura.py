"""
KPI summary tables: read path for `kpi_venta_mes` (odd/motored-kpis-resumenes, R3).

Answers FROM `kpi_venta_mes` the same questions the live queries of
`tablero_asesores_consultas` / `tablero_kpis_consultas` answer from `venta_detalle`:
the cube (asesor, sucursal and total dimensions), the monthly growth window, the
cost of sales, the months available and the sales side of the personas. The result
types are the live ones, so callers cannot tell the source.

The table stores only dimensions that do not depend on Configuracion, so the
Configuracion of the request is applied here, at READ time, exactly as the live
queries apply it:
- a line is recognized when `linea_norm IN reglas.lineas`, otherwise it is NULL;
- a client is HMCL when `nit_especial IN reglas.hmcl_nits`, Tecnired when
  `nit_especial` is in `cliente_tecnired` (NULL counts as neither);
- months are the filter's `[inicio, fin)` ranges over `anio_mes`, plus the stores;
- the asesor row comes from `q._expr_clave` over the master `vendedor`, fed with
  `kpi_venta_mes.vendedor_norm` instead of the sale's column;
- the HMCL mode is NOT applied by the cube nor the growth window (the caller
  filters in Python, so HMCL sales stay available) but IS applied by the personas.

Switch: `MOTORED_KPI_RESUMEN_ENABLED` AND usable summaries (the state row exists,
was fully rebuilt at least once and is not dirty). Otherwise every function here
delegates to the untouched live query, which is also the fallback. The dispatch
functions (`cubo`, `ventana_mensual`, `costo_venta`, `meses`, `personas`) are what
the callers use; the `_resumen` ones read the summary unconditionally.

Costs come baked into the summary at the latest inventory cut, so the cost reads
ignore the `fecha_corte` argument the live queries take (callers pass the latest cut).
"""
import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy import Date, String, and_, case, cast, false, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.motored.models.cliente_tecnired import ClienteTecnired
from app.motored.models.kpi_resumen import KpiClienteMes as C
from app.motored.models.kpi_resumen import KpiFacturaFirma as F
from app.motored.models.kpi_resumen import KpiInventarioCorte as Corte
from app.motored.models.kpi_resumen import KpiVentaMes as V
from app.motored.models.sucursal import Sucursal
from app.motored.models.vendedor import Vendedor
from app.motored.services import kpi_resumen
from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_asesores_consultas as q
from app.motored.services import tablero_kpis_consultas as qk
from app.motored.services.tablero_asesores import (
    CLAVE_TOTAL, DIM_ASESOR, DIM_TOTAL, FilaClientes, FilaCubo, FilaFacturas, FilaPersona, Filtro,
)


async def usar_resumen(db: AsyncSession) -> bool:
    """True when the summaries should answer: switch on, built and not dirty. The
    switch is checked first, so with it off no query is made."""
    if not settings.MOTORED_KPI_RESUMEN_ENABLED:
        return False
    estado = await kpi_resumen.estado(db)
    return estado is not None and estado.ultima_reconstruccion_total is not None and not estado.sucio


# --- Expressions over kpi_venta_mes ----------------------------------------------------------


def _mes(tabla=V):
    return func.to_char(tabla.anio_mes, "YYYY-MM")


def _linea(reglas: t.Reglas):
    """The line under the request's Configuracion; NULL when it is not a recognized one."""
    return case((V.linea_norm.in_(list(reglas.lineas)), V.linea_norm), else_=None)


def _es_hmcl(reglas: t.Reglas, columna=V.nit_especial):
    return func.coalesce(columna.in_(list(reglas.hmcl_nits)), false())


def _es_tecnired():
    return func.coalesce(V.nit_especial.in_(select(ClienteTecnired.nit)), false())


def _dimension(dimension: str, reglas: t.Reglas, tabla=V, vendedor_norm=None):
    return q._expr_dimension(
        dimension, reglas, sucursal=tabla.sucursal_id,
        vendedor_norm=tabla.vendedor_norm if vendedor_norm is None else vendedor_norm)


def _con_vendedor(consulta, vendedor_norm):
    """The live outer join with the master vendedor (active rows), fed with the summary's column."""
    return consulta.outerjoin(Vendedor, (Vendedor.nombre_norm == vendedor_norm) & Vendedor.activo.is_(True))


def _donde_periodo(consulta, tabla, filtro: Filtro, mes=None):
    """Months (the filter's `[inicio, fin)` ranges over `anio_mes`, or over `mes`) and stores."""
    mes = tabla.anio_mes if mes is None else mes
    consulta = consulta.where(or_(*[and_(mes >= inicio, mes < fin) for inicio, fin in filtro.rangos]))
    if filtro.sucursal_ids:
        consulta = consulta.where(tabla.sucursal_id.in_(sorted(filtro.sucursal_ids, key=str)))
    return consulta


def _donde_hmcl(consulta, filtro: Filtro, columna):
    """The HMCL mode over `columna` (the NIT the line / invoice / client is billed to)."""
    if filtro.modo_hmcl == t.HMCL_SOLO:
        return consulta.where(_es_hmcl(filtro.reglas, columna))
    if filtro.modo_hmcl == t.HMCL_EXCLUIR:
        return consulta.where(~_es_hmcl(filtro.reglas, columna))
    return consulta


def _desde(consulta, filtro: Filtro, *, tabla=V, con_vendedor=False, solo_lineas_reconocidas=False,
           aplicar_hmcl=False, columna_hmcl=None):
    """FROM/WHERE of every read: the live `_desde_ventas` over the summary table."""
    consulta = consulta.select_from(tabla)
    if con_vendedor:
        consulta = _con_vendedor(consulta, tabla.vendedor_norm)
    consulta = _donde_periodo(consulta, tabla, filtro)
    if aplicar_hmcl:
        consulta = _donde_hmcl(consulta, filtro, tabla.nit_especial if columna_hmcl is None else columna_hmcl)
    if solo_lineas_reconocidas:
        consulta = consulta.where(tabla.linea_norm.in_(list(filtro.reglas.lineas)))
    return consulta


# --- Reads (summary) ---------------------------------------------------------------------------


async def cubo_resumen(db: AsyncSession, filtro: Filtro, dimension: str = DIM_ASESOR) -> List[FilaCubo]:
    """`q.consultar_cubo` from the summary. The total dimension has no key to group by."""
    reglas = filtro.reglas
    clave = _dimension(dimension, reglas).label("clave")
    columnas = [_mes().label("mes"), _linea(reglas).label("linea"), _es_hmcl(reglas).label("es_hmcl"),
                _es_tecnired().label("es_tecnired"), V.es_mostrador, V.con_costo]
    consulta = select(
        clave, *columnas, func.sum(V.venta), func.sum(V.bruto), func.sum(V.descuentos), func.sum(V.cantidad),
        func.sum(V.lineas), func.sum(V.costo), func.sum(V.costo_estimado),
    ).group_by(*columnas, *([] if dimension == DIM_TOTAL else [clave]))
    consulta = _desde(consulta, filtro, con_vendedor=dimension == DIM_ASESOR)
    return [
        FilaCubo(clave_, mes, linea, hmcl, tec, mostr, costo_ok, Decimal(venta), Decimal(bruto), Decimal(desc),
                 Decimal(cant), int(n), Decimal(costo), Decimal(estimado))
        for clave_, mes, linea, hmcl, tec, mostr, costo_ok, venta, bruto, desc, cant, n, costo, estimado
        in (await db.execute(consulta)).all()
    ]


async def ventana_mensual_resumen(db: AsyncSession, filtro: Filtro, dimension: str) -> List[q.FilaVentana]:
    """`q.consultar_ventana_mensual` from the summary."""
    reglas = filtro.reglas
    columnas = [_dimension(dimension, reglas).label("clave"), _mes().label("mes"), _es_hmcl(reglas).label("es_hmcl")]
    consulta = _desde(
        select(*columnas, func.sum(V.venta)).group_by(*columnas), filtro,
        con_vendedor=dimension == DIM_ASESOR, solo_lineas_reconocidas=True)
    return [q.FilaVentana(c, m, bool(h), Decimal(v)) for c, m, h, v in (await db.execute(consulta)).all()]


async def costo_venta_resumen(db: AsyncSession, filtro: Filtro) -> Tuple[Dict[str, Decimal], int]:
    """`qk.consultar_costo_venta` from the summary: the cost per store over the 3 calendar months."""
    ventana, dias = qk.filtro_costo_venta(filtro)
    tienda = cast(V.sucursal_id, String)
    consulta = _desde(select(tienda, func.sum(V.costo)).group_by(tienda), ventana)
    return {s: Decimal(v) for s, v in (await db.execute(consulta)).all()}, dias


async def meses_resumen(db: AsyncSession) -> List[str]:
    """`q.meses_disponibles` from the summary."""
    mes = _mes()
    return [m for (m,) in (await db.execute(select(mes).group_by(mes).order_by(mes))).all()]


async def personas_resumen(db: AsyncSession, filtro: Filtro) -> List[FilaPersona]:
    """`q.consultar_personas` from the summary (this one does apply the HMCL mode)."""
    reglas = filtro.reglas
    columnas = [q._expr_clave(reglas, V.vendedor_norm).label("clave"),
                q._expr_identidad(V.vendedor_norm).label("identidad"),
                V.vendedor_norm, Vendedor.nombre, Vendedor.cargo, Sucursal.nombre]
    consulta = _desde(
        select(*columnas, func.sum(V.venta)).group_by(*columnas), filtro,
        con_vendedor=True, solo_lineas_reconocidas=True, aplicar_hmcl=True,
    ).outerjoin(Sucursal, Sucursal.id == Vendedor.sucursal_id)
    filas = [
        t.FilaVendedorVenta(clave_, identidad_, nombre, cargo, punto, Decimal(venta))
        for clave_, identidad_, _norm, nombre, cargo, punto, venta in (await db.execute(consulta)).all()
    ]
    return t.construir_personas(filas)


# --- Invoices and clients ---------------------------------------------------------------------


def _factura_regular(filtro: Filtro, dimension: str):
    """One row per `(invoice-group, summary row)` of the plain invoices: the lines of its
    signature that the request's Configuracion recognizes, with the marks per line."""
    reglas = filtro.reglas
    desanidada = func.unnest(F.firma).table_valued("linea").render_derived()
    linea = desanidada.c.linea
    clave = _dimension(dimension, reglas, F).label("clave")
    marcas = [func.max(case((linea == nombre, 1), else_=0)).label(f"l{i}") for i, nombre in enumerate(reglas.lineas)]
    consulta = select(F.id.label("fila"), clave, F.n_facturas.label("n"), func.count().label("distintas"), *marcas)
    consulta = consulta.select_from(F).join(desanidada, true())
    if dimension == DIM_ASESOR:
        consulta = _con_vendedor(consulta, F.vendedor_norm)
    consulta = _donde_periodo(consulta, F, filtro)
    consulta = _donde_hmcl(consulta, filtro, F.nit_especial)
    consulta = consulta.where(F.nit_especial.is_distinct_from(kpi_resumen.NIT_FACTURA_IRREGULAR),
                              linea.in_(list(reglas.lineas)))
    return consulta.group_by(F.id, F.n_facturas, *([clave] if dimension != DIM_TOTAL else []))


def _factura_irregular(filtro: Filtro, dimension: str):
    """The same for the invoices that span months, vendors or special NITs: their signature
    holds one `month|line|nit|vendedor` token per combination (see `kpi_resumen`), which is
    filtered and grouped here exactly as the live query does line by line."""
    reglas = filtro.reglas
    desanidada = func.unnest(F.firma).table_valued("marca").render_derived()
    marca = desanidada.c.marca
    mes = cast(func.split_part(marca, "|", 1), Date)
    linea = func.split_part(marca, "|", 2)
    nit = func.nullif(func.split_part(marca, "|", 3), "")
    vendedor = func.regexp_replace(marca, r"^[^|]*\|[^|]*\|[^|]*\|", "")
    clave = _dimension(dimension, reglas, F, vendedor).label("clave")
    marcas = [func.max(case((linea == nombre, 1), else_=0)).label(f"l{i}") for i, nombre in enumerate(reglas.lineas)]
    consulta = select(
        F.id.label("fila"), clave, F.n_facturas.label("n"), func.count(func.distinct(linea)).label("distintas"),
        *marcas)
    consulta = consulta.select_from(F).join(desanidada, true())
    if dimension == DIM_ASESOR:
        consulta = _con_vendedor(consulta, vendedor)
    consulta = _donde_periodo(consulta, F, filtro, mes=mes)
    consulta = _donde_hmcl(consulta, filtro, nit)
    consulta = consulta.where(F.nit_especial == kpi_resumen.NIT_FACTURA_IRREGULAR, linea.in_(list(reglas.lineas)))
    return consulta.group_by(F.id, F.n_facturas, *([clave] if dimension != DIM_TOTAL else []))


async def facturas_resumen(db: AsyncSession, filtro: Filtro, *, dimension: str) -> List[FilaFacturas]:
    """`q.consultar_facturas` from `kpi_factura_firma`. An invoice counts once per group, like
    live: a summary row stands for `n_facturas` identical invoices (the weight of every sum)."""
    reglas = filtro.reglas
    por_grupo = dimension != DIM_TOTAL
    todas = _factura_regular(filtro, dimension).union_all(_factura_irregular(filtro, dimension)).subquery("por_factura")
    externa = select(
        todas.c.clave if por_grupo else q._constante(CLAVE_TOTAL),
        func.coalesce(func.sum(todas.c.n), 0),
        func.coalesce(func.sum(case((todas.c.distintas > 1, todas.c.n), else_=0)), 0),
        *[func.coalesce(func.sum(todas.c[f"l{i}"] * todas.c.n), 0) for i in range(len(reglas.lineas))],
    )
    if por_grupo:
        externa = externa.group_by(todas.c.clave)
    return [
        FilaFacturas(fila[0], int(fila[1]), int(fila[2]), tuple(int(n) for n in fila[3:]))
        for fila in (await db.execute(externa)).all()
    ]


def _desde_clientes(consulta, filtro: Filtro, *, con_vendedor=False):
    """Recognized lines only, the HMCL mode applied to the client (as live does)."""
    return _desde(consulta, filtro, tabla=C, con_vendedor=con_vendedor, solo_lineas_reconocidas=True,
                  aplicar_hmcl=True, columna_hmcl=C.cliente_norm)


async def clientes_resumen(db: AsyncSession, filtro: Filtro, *, dimension: str) -> List[FilaClientes]:
    """`q.consultar_clientes` from `kpi_cliente_mes`: distinct clients and top-5 sale share."""
    por_grupo = dimension != DIM_TOTAL
    clave = _dimension(dimension, filtro.reglas, C).label("clave")
    interna = _desde_clientes(
        select(clave, func.sum(C.venta).label("venta")).group_by(C.cliente_norm, *([clave] if por_grupo else [])),
        filtro, con_vendedor=dimension == DIM_ASESOR).subquery("por_cliente")
    return q._filas_de_clientes(await db.execute(q._agregar_clientes(interna, por_grupo)))


def _desde_tecnired(consulta, filtro: Filtro):
    """Sales of Tecnired clients (recognized lines), with the filter."""
    return _desde_clientes(consulta, filtro).where(C.cliente_norm.in_(select(ClienteTecnired.nit)))


async def clientes_tecnired_resumen(db: AsyncSession, filtro: Filtro) -> Tuple[int, Dict[str, int]]:
    """`qk.consultar_clientes_tecnired` from `kpi_cliente_mes`."""
    total = await db.execute(_desde_tecnired(select(func.count(func.distinct(C.cliente_norm))), filtro))
    mes = _mes(C)
    por_mes = await db.execute(
        _desde_tecnired(select(mes, func.count(func.distinct(C.cliente_norm))).group_by(mes), filtro))
    return int(total.scalar() or 0), {m: int(n) for m, n in por_mes.all()}


async def top_tecnired_resumen(
    db: AsyncSession, filtro: Filtro, limite: int = qk.TOP_TECNIRED,
) -> List[qk.FilaTopTecnired]:
    """`qk.consultar_top_tecnired` from `kpi_cliente_mes`."""
    venta = func.sum(C.venta)
    consulta = _desde_tecnired(select(ClienteTecnired.nit, ClienteTecnired.razon_social, venta), filtro)
    consulta = (
        consulta.join(ClienteTecnired, ClienteTecnired.nit == C.cliente_norm)
        .group_by(ClienteTecnired.nit, ClienteTecnired.razon_social)
        .order_by(venta.desc(), ClienteTecnired.nit)
        .limit(limite)
    )
    return [qk.FilaTopTecnired(nit, razon, Decimal(v)) for nit, razon, v in (await db.execute(consulta)).all()]


# --- Inventory and the cost cut ---------------------------------------------------------------


async def inventario_resumen(
    db: AsyncSession, filtro: Filtro, fecha_corte: Optional[datetime.date],
) -> List[qk.FilaInventario]:
    """`qk.consultar_inventario` from `kpi_inventario_corte` (only the latest cut is kept)."""
    if fecha_corte is None:
        return []
    consulta = select(
        cast(Corte.sucursal_id, String), Corte.valor, Corte.lineas_sin_costo, Corte.lineas_costo_maestro,
    ).where(Corte.fecha_corte == fecha_corte)
    if filtro.sucursal_ids:
        consulta = consulta.where(Corte.sucursal_id.in_(sorted(filtro.sucursal_ids, key=str)))
    return [qk.FilaInventario(s, Decimal(v), int(n), int(m)) for s, v, n, m in (await db.execute(consulta)).all()]


async def fecha_corte_costos_resumen(db: AsyncSession) -> Optional[datetime.date]:
    """`q.fecha_corte_costos` from the summary: the cut of `kpi_inventario_corte` (empty without inventory)."""
    return (await db.execute(select(func.max(Corte.fecha_corte)))).scalar()


# --- Dispatch: the summary when usable, the live query otherwise -----------------------------


async def cubo(
    db: AsyncSession, filtro: Filtro, fecha_corte: Optional[datetime.date], dimension: str = DIM_ASESOR,
) -> List[FilaCubo]:
    if await usar_resumen(db):
        return await cubo_resumen(db, filtro, dimension)
    return await q.consultar_cubo(db, filtro, fecha_corte, dimension)


async def ventana_mensual(db: AsyncSession, filtro: Filtro, dimension: str) -> List[q.FilaVentana]:
    if await usar_resumen(db):
        return await ventana_mensual_resumen(db, filtro, dimension)
    return await q.consultar_ventana_mensual(db, filtro, dimension)


async def costo_venta(
    db: AsyncSession, filtro: Filtro, fecha_corte: Optional[datetime.date],
) -> Tuple[Dict[str, Decimal], int]:
    if await usar_resumen(db):
        return await costo_venta_resumen(db, filtro)
    return await qk.consultar_costo_venta(db, filtro, fecha_corte)


async def meses(db: AsyncSession) -> List[str]:
    if await usar_resumen(db):
        return await meses_resumen(db)
    return await q.meses_disponibles(db)


async def personas(db: AsyncSession, filtro: Filtro) -> List[FilaPersona]:
    if await usar_resumen(db):
        return await personas_resumen(db, filtro)
    return await q.consultar_personas(db, filtro)


async def facturas(db: AsyncSession, filtro: Filtro, *, dimension: str) -> List[FilaFacturas]:
    if await usar_resumen(db):
        return await facturas_resumen(db, filtro, dimension=dimension)
    return await q.consultar_facturas(db, filtro, dimension=dimension)


async def clientes(db: AsyncSession, filtro: Filtro, *, dimension: str) -> List[FilaClientes]:
    if await usar_resumen(db):
        return await clientes_resumen(db, filtro, dimension=dimension)
    return await q.consultar_clientes(db, filtro, dimension=dimension)


async def clientes_tecnired(db: AsyncSession, filtro: Filtro) -> Tuple[int, Dict[str, int]]:
    if await usar_resumen(db):
        return await clientes_tecnired_resumen(db, filtro)
    return await qk.consultar_clientes_tecnired(db, filtro)


async def top_tecnired(db: AsyncSession, filtro: Filtro, limite: int = qk.TOP_TECNIRED) -> List[qk.FilaTopTecnired]:
    if await usar_resumen(db):
        return await top_tecnired_resumen(db, filtro, limite)
    return await qk.consultar_top_tecnired(db, filtro, limite)


async def inventario(
    db: AsyncSession, filtro: Filtro, fecha_corte: Optional[datetime.date],
) -> List[qk.FilaInventario]:
    """The summary holds one cut only: a different date (a stale summary) is answered live."""
    if fecha_corte is not None and await usar_resumen(db):
        if await fecha_corte_costos_resumen(db) == fecha_corte:
            return await inventario_resumen(db, filtro, fecha_corte)
    return await qk.consultar_inventario(db, filtro, fecha_corte)


async def fecha_corte_costos(db: AsyncSession) -> Optional[datetime.date]:
    if await usar_resumen(db):
        return await fecha_corte_costos_resumen(db)
    return await q.fecha_corte_costos(db)
