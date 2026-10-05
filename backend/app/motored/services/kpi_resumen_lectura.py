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

from sqlalchemy import String, and_, case, cast, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.motored.models.cliente_tecnired import ClienteTecnired
from app.motored.models.kpi_resumen import KpiVentaMes as V
from app.motored.models.sucursal import Sucursal
from app.motored.models.vendedor import Vendedor
from app.motored.services import kpi_resumen
from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_asesores_consultas as q
from app.motored.services import tablero_kpis_consultas as qk
from app.motored.services.tablero_asesores import DIM_ASESOR, DIM_TOTAL, FilaCubo, FilaPersona, Filtro


async def usar_resumen(db: AsyncSession) -> bool:
    """True when the summaries should answer: switch on, built and not dirty. The
    switch is checked first, so with it off no query is made."""
    if not settings.MOTORED_KPI_RESUMEN_ENABLED:
        return False
    estado = await kpi_resumen.estado(db)
    return estado is not None and estado.ultima_reconstruccion_total is not None and not estado.sucio


# --- Expressions over kpi_venta_mes ----------------------------------------------------------


def _mes():
    return func.to_char(V.anio_mes, "YYYY-MM")


def _linea(reglas: t.Reglas):
    """The line under the request's Configuracion; NULL when it is not a recognized one."""
    return case((V.linea_norm.in_(list(reglas.lineas)), V.linea_norm), else_=None)


def _es_hmcl(reglas: t.Reglas):
    return func.coalesce(V.nit_especial.in_(list(reglas.hmcl_nits)), false())


def _es_tecnired():
    return func.coalesce(V.nit_especial.in_(select(ClienteTecnired.nit)), false())


def _dimension(dimension: str, reglas: t.Reglas):
    return q._expr_dimension(dimension, reglas, sucursal=V.sucursal_id, vendedor_norm=V.vendedor_norm)


def _desde(consulta, filtro: Filtro, *, con_vendedor=False, solo_lineas_reconocidas=False, aplicar_hmcl=False):
    """FROM/WHERE of every read: the live `_desde_ventas` over the summary table."""
    reglas = filtro.reglas
    consulta = consulta.select_from(V)
    if con_vendedor:
        consulta = consulta.outerjoin(
            Vendedor, (Vendedor.nombre_norm == V.vendedor_norm) & Vendedor.activo.is_(True))
    consulta = consulta.where(or_(*[and_(V.anio_mes >= inicio, V.anio_mes < fin) for inicio, fin in filtro.rangos]))
    if filtro.sucursal_ids:
        consulta = consulta.where(V.sucursal_id.in_(sorted(filtro.sucursal_ids, key=str)))
    if aplicar_hmcl and filtro.modo_hmcl == t.HMCL_SOLO:
        consulta = consulta.where(_es_hmcl(reglas))
    elif aplicar_hmcl and filtro.modo_hmcl == t.HMCL_EXCLUIR:
        consulta = consulta.where(~_es_hmcl(reglas))
    if solo_lineas_reconocidas:
        consulta = consulta.where(V.linea_norm.in_(list(reglas.lineas)))
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
