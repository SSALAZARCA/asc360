"""
Motored "Inicio": the same four figures for every role that reaches it.

`construir_inicio` owns no business rule: every number comes from an
existing read.

- `ventas_mes` / `ventas_anio`: the "Repuestos" sales of the last complete
  month and of January to today (Bogota dates), all stores, HMCL included.
  They are the KPI Ventas tab's own figure, `total.venta.por_linea`
  (`tablero_kpis.calcular_kpis_ventas`): the same filter
  (`tablero_asesores_consultas.cargar_filtro`), the same cube
  (`kpi_resumen_lectura.cubo`, the summary or the live query) and the
  same accumulation (`tablero_asesores.acumular_cubo`). So a sale is
  `valor_bruto - valor_descuentos`, annulled loads never count, and the
  line is `referencia.linea_comercial` normalized and recognized only when
  it is one of the configured `lineas_comerciales`. The months are whole
  months; the current one has no sales after today.
- `puntos_venta`: the active principal stores
  (`tablero_kpis_consultas.consultar_tiendas_activas`, the KPI's store
  filter); associated stores are seen inside their principal.
- `asesores`: the active vendedores of the master.

Every figure runs on its own savepoint and fails soft: an exception is
logged and the figure answers `{"disponible": false}`, never a 500 for the
whole page. Read only: nothing here commits.
"""
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Awaitable, Callable, Dict, List, Optional

from sqlalchemy import func, select

from app.motored.models.vendedor import Vendedor
from app.motored.services import kpi_resumen_lectura
from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_asesores_consultas
from app.motored.services import tablero_kpis_consultas
from app.motored.services.reloj import hoy_bogota

logger = logging.getLogger("motored.inicio")

# The normalized name of the line in `tablero_asesores.LINEAS`.
LINEA_REPUESTOS = "REPUESTOS"


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


async def venta_repuestos(db, meses: List[str]) -> float:
    """The KPI Ventas tab's Repuestos sales of `meses` (AAAA-MM), all
    stores, HMCL included, rounded like the tab (`_dinero`)."""
    filtro = await tablero_asesores_consultas.cargar_filtro(
        db, meses, t.HMCL_INCLUIR, None)
    # By store, like the tab: a total-dimension cube is keyed TOTAL and
    # `acumular_cubo` would add it twice.
    cubo = await kpi_resumen_lectura.cubo(
        db, filtro, None, t.DIM_SUCURSAL)
    acumulados, _ = t.acumular_cubo(cubo, filtro.reglas)
    total = acumulados[t.CLAVE_TOTAL]
    return float(round(total.venta_por_linea.get(LINEA_REPUESTOS, 0), 2))


async def _ventas_mes(ctx: Contexto) -> Dict[str, Any]:
    """The last complete month: the one before today's."""
    mes = _mes(ctx.hoy.replace(day=1) - timedelta(days=1))
    return {"valor": await venta_repuestos(ctx.db, [mes]), "mes": mes}


async def _ventas_anio(ctx: Contexto) -> Dict[str, Any]:
    """January 1 to today: January to today's month."""
    meses = [f"{ctx.hoy.year}-{m:02d}" for m in range(1, ctx.hoy.month + 1)]
    return {
        "valor": await venta_repuestos(ctx.db, meses),
        "desde": ctx.hoy.replace(month=1, day=1).isoformat(),
        "hasta": ctx.hoy.isoformat(),
    }


async def _puntos_venta(ctx: Contexto) -> Dict[str, Any]:
    tiendas = await tablero_kpis_consultas.consultar_tiendas_activas(ctx.db)
    return {"cantidad": len(tiendas)}


async def _asesores(ctx: Contexto) -> Dict[str, Any]:
    fila = (await ctx.db.execute(
        select(func.count(Vendedor.id))
        .where(Vendedor.activo.is_(True)))).first()
    return {"cantidad": int(fila[0] or 0)}


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
