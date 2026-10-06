"""
Motored "Inicio": the same four figures for every role that reaches it.

`construir_inicio` owns no business rule: every number comes from an
existing KPI read, with the KPI's defaults (all stores, HMCL included).

- `ventas_mes` / `ventas_anio`: the KPI Ventas tab's headline "Venta N
  meses", `total.venta.total` (`tablero_kpis.calcular_kpis_ventas`): the
  sum of every configured commercial line (repuestos, accesorios, llantas,
  lubricantes, baterias, GPS, cascos). The same filter
  (`tablero_asesores_consultas.cargar_filtro`), cost cut and cube
  (`kpi_resumen_lectura`, the summary or the live query), HMCL mode
  (`tablero_asesores.filtrar_cubo_por_hmcl`) and accumulation
  (`tablero_asesores.acumular_cubo`). `ventas_mes` is the last complete
  month; `ventas_anio` is the KPI's "Año corrido": January to the last
  month with sales (`tablero_kpis.calcular_opciones`'s `ultimo_mes`) of
  that month's year.
- `puntos_venta`: the active principal stores
  (`tablero_kpis_consultas.consultar_tiendas_activas`, the KPI's store
  filter); associated stores are seen inside their principal.
- `asesores`: KPIs > Asesores "con venta" for the last complete month: the
  person rows of the asesor cube (a cargo of an asesor, one per cedula)
  with a positive sale in a commercial line.

Every figure runs on its own savepoint and fails soft: an exception is
logged and the figure answers `{"disponible": false}`, never a 500 for the
whole page. Read only: nothing here commits.
"""
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Awaitable, Callable, Dict, List, Optional

from app.motored.services import kpi_resumen_lectura
from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_asesores_consultas
from app.motored.services import tablero_kpis_consultas
from app.motored.services.reloj import hoy_bogota

logger = logging.getLogger("motored.inicio")


@dataclass
class Contexto:
    """One request: the session and Bogota's today."""

    db: Any
    hoy: date

    @classmethod
    def de(cls, db, hoy: Optional[date] = None) -> "Contexto":
        return cls(db=db, hoy=hoy or hoy_bogota())


def _mes(fecha: date) -> str:
    return fecha.strftime("%Y-%m")


def _ultimo_mes_completo(hoy: date) -> str:
    return _mes(hoy.replace(day=1) - timedelta(days=1))


async def _acumulados(db, meses: List[str], dimension: str):
    """`acumular_cubo` of `meses` (AAAA-MM) exactly as the KPI tabs read
    it: all stores, HMCL included, the KPI's cost cut."""
    filtro = await tablero_asesores_consultas.cargar_filtro(
        db, meses, t.HMCL_INCLUIR, None)
    corte = await kpi_resumen_lectura.fecha_corte_costos(db)
    cubo = await kpi_resumen_lectura.cubo(db, filtro, corte, dimension)
    acumulados, _ = t.acumular_cubo(
        t.filtrar_cubo_por_hmcl(cubo, filtro.modo_hmcl), filtro.reglas)
    return acumulados


async def venta_kpi(db, meses: List[str]) -> float:
    """The KPI Ventas tab's `total.venta.total` of `meses`, rounded like
    the tab (`_dinero`)."""
    # By store, like the tab: a total-dimension cube is keyed TOTAL and
    # `acumular_cubo` would add it twice.
    acumulados = await _acumulados(db, meses, t.DIM_SUCURSAL)
    return float(round(acumulados[t.CLAVE_TOTAL].venta, 2))


async def _ventas_mes(ctx: Contexto) -> Dict[str, Any]:
    """The last complete month: the one before today's."""
    mes = _ultimo_mes_completo(ctx.hoy)
    return {"valor": await venta_kpi(ctx.db, [mes]), "mes": mes}


async def _ventas_anio(ctx: Contexto) -> Dict[str, Any]:
    """The KPI's "Año corrido": January to the last month with sales."""
    disponibles = await kpi_resumen_lectura.meses(ctx.db)
    if not disponibles:
        return {"valor": 0.0, "desde": None, "hasta": None}
    hasta = disponibles[-1]
    anio, ultimo = hasta[:4], int(hasta[5:7])
    meses = [f"{anio}-{m:02d}" for m in range(1, ultimo + 1)]
    return {
        "valor": await venta_kpi(ctx.db, meses),
        "desde": meses[0],
        "hasta": hasta,
    }


async def _puntos_venta(ctx: Contexto) -> Dict[str, Any]:
    tiendas = await tablero_kpis_consultas.consultar_tiendas_activas(ctx.db)
    return {"cantidad": len(tiendas)}


async def _asesores(ctx: Contexto) -> Dict[str, Any]:
    """KPIs > Asesores "con venta" (`venta.total > 0` of each PERSONA row)
    for the last complete month."""
    mes = _ultimo_mes_completo(ctx.hoy)
    acumulados = await _acumulados(ctx.db, [mes], t.DIM_ASESOR)
    cantidad = sum(
        1 for clave, acum in acumulados.items()
        if t.es_clave_persona(clave) and round(acum.venta, 2) > 0)
    return {"cantidad": cantidad, "mes": mes}


Constructor = Callable[[Contexto], Awaitable[Dict[str, Any]]]

CONSTRUCTORES: Dict[str, Constructor] = {
    "ventas_mes": _ventas_mes,
    "ventas_anio": _ventas_anio,
    "puntos_venta": _puntos_venta,
    "asesores": _asesores,
}


async def _figura(ctx: Contexto, nombre: str) -> Dict[str, Any]:
    """One figure on its own savepoint: a failed query cannot poison the
    transaction for the next figure."""
    try:
        async with ctx.db.begin_nested():
            datos = await CONSTRUCTORES[nombre](ctx)
    except Exception:
        logger.exception("inicio: figure %s is unavailable", nombre)
        return {"disponible": False}
    return {"disponible": True, **datos}


async def construir_inicio(
    db, hoy: Optional[date] = None,
) -> Dict[str, Any]:
    """`{hoy, ventas_mes, ventas_anio, puntos_venta, asesores}`, the same
    for every role."""
    ctx = Contexto.de(db, hoy)
    respuesta: Dict[str, Any] = {"hoy": ctx.hoy.isoformat()}
    for nombre in CONSTRUCTORES:
        respuesta[nombre] = await _figura(ctx, nombre)
    return respuesta
