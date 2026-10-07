"""
Motored -- the light month-to-date read behind the asesor report sends
(odd/motored-reporte-diario-asesor, perf fix).

`ventas_del_mes(db, fecha)` answers, for the month of `fecha` up to
`fecha`, who the daily report builder (`reportes_asesores`) would list and
the two numbers the Lore message carries (`cumplimiento_pct`,
`total_a_pagar`), without building the KPI board, the year trend or any
asesor detail.

It runs the same liquidation the builder runs
(`tablero_kpis.liquidar_cubo_del_mes`) over the same inputs, restricted to
the one month the liquidation reads:

- the asesores cube of the month (HMCL included), from the KPI summary on
  the same rule as the builder (usable AND nothing loaded after `fecha`),
  live otherwise. No cost cut: the liquidation reads sales, not costs;
- the month's budgets, an associated store rolled into its principal.

So the cédulas (`reportes` plus `sin_presupuesto`), the names, the stores,
the numbers and the `sin_cedula` count are the builder's by construction
(`tests/motored/pg_real/test_reporte_asesor_ventas_pg.py`).
"""
import datetime
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, NamedTuple, Optional

from app.motored.services import kpi_resumen_lectura as lectura
from app.motored.services import presupuestos as pres
from app.motored.services import tablero_asesores_consultas as q
from app.motored.services import tablero_kpis as k
from app.motored.services.sucursal_grupo import principal_de
from app.motored.services.tablero_asesor_detalle import pesos
from app.motored.services.tablero_asesores import (
    DIM_ASESOR, HMCL_INCLUIR, Filtro,
)


@dataclass(frozen=True)
class VentasDelMes:
    """`asesores` is `{cedula: {nombre, tienda, con_reporte,
    cumplimiento_pct, total_a_pagar}}`; `sin_cedula` counts the sellers
    whose sales match no valid cédula."""
    asesores: Dict[str, Dict[str, Any]]
    sin_cedula: int

    @property
    def reportes(self) -> Dict[str, Dict[str, Any]]:
        """Only the asesores with a report (a budget this month)."""
        return {c: x for c, x in self.asesores.items() if x["con_reporte"]}

    @property
    def sin_presupuesto(self) -> int:
        return sum(1 for x in self.asesores.values()
                   if not x["con_reporte"])


VACIO = VentasDelMes({}, 0)


def armar_ventas(asesores: Iterable[Dict[str, Any]],
                 sin_presupuesto: Iterable[Dict[str, Any]],
                 sin_cedula: Mapping[str, Any]) -> VentasDelMes:
    """PURE: one liquidation (`liquidar_cubo_del_mes`) in the light shape.
    Money is whole pesos, half up, like the builder's report."""
    filas = {
        a["cedula"]: {
            "nombre": a["nombre"], "tienda": a["tienda"],
            "con_reporte": True,
            "cumplimiento_pct": a["cumplimiento_pct"],
            "total_a_pagar": pesos(a["total_a_pagar"]),
        }
        for a in asesores
    }
    for x in sin_presupuesto:
        filas.setdefault(x["cedula"], {
            "nombre": x["nombre"], "tienda": None, "con_reporte": False,
            "cumplimiento_pct": None, "total_a_pagar": None,
        })
    return VentasDelMes(filas, len(sin_cedula))


class _Mes(NamedTuple):
    mes: str
    primero: datetime.date
    fecha_datos: Optional[datetime.date]
    filtro: Filtro
    resumen: bool


async def _mes(db, fecha: datetime.date) -> _Mes:
    """The month of `fecha` up to `fecha`, the date of its last loaded
    sale and the source, on the builder's rules (`_periodo`)."""
    mes = f"{fecha:%Y-%m}"
    ultima = await q.ultima_fecha_venta(db, mes)
    fecha_datos = ultima
    if ultima is not None and ultima > fecha:
        fecha_datos = await q.ultima_fecha_venta(db, mes, hasta=fecha)
    primero = fecha.replace(day=1)
    base = await q.cargar_filtro(db, [mes], HMCL_INCLUIR)
    filtro = base._replace(
        rangos=((primero, fecha + datetime.timedelta(days=1)),))
    resumen = fecha_datos == ultima and await lectura.usar_resumen(db)
    return _Mes(mes, primero, fecha_datos, filtro, resumen)


async def _cubo(db, m: _Mes):
    if m.resumen:
        return await lectura.cubo_resumen(db, m.filtro, DIM_ASESOR)
    return await q.consultar_cubo(db, m.filtro, None, DIM_ASESOR)


async def _presupuestos(db, m: _Mes):
    crudos = await pres.presupuesto_por_asesor(db, m.primero, m.primero)
    return k.presupuestos_del_rango(
        crudos, [m.mes], None, await principal_de(db))


async def ventas_del_mes(db, fecha: datetime.date) -> VentasDelMes:
    """Who the builder lists for `fecha` and their message numbers. A
    month without a sale up to `fecha` lists nobody."""
    m = await _mes(db, fecha)
    if m.fecha_datos is None:
        return VACIO
    _, asesores, advertencias, sin_cedula = await k.liquidar_cubo_del_mes(
        db, m.filtro, m.mes, await _cubo(db, m), await _presupuestos(db, m))
    return armar_ventas(
        asesores, advertencias["sin_presupuesto"], sin_cedula)
