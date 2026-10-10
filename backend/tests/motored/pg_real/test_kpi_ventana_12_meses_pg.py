"""
The monthly charts of the KPI tabs do not follow the Período filter (odd/motored-kpis-ventana-12-meses), against
a real Postgres (opt-in). They always cover the last 12 months ending at the last month with sales.

World: `test_tablero_asesor_detalle_pg.Mundo` (2097, Jan-Mar). Network sales: Jan 1700, Feb 1500, Mar 1700;
Norte (Ana + Beto) 1500 / 1300 / 1600; Tecnired (Feb only): Ana 600 + 400, Beto 300 = 1300 from 2 clients.
Ana's cumplimiento: 1.0 / 1.0 / 0.875. Every check asks for March ONLY and still gets the three months.
"""
import pytest

from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_asesores_consultas as q
from app.motored.services import tablero_kpis as k
from tests.motored.pg_real.test_tablero_asesor_detalle_pg import MESES, Mundo
from tests.motored.pg_real.test_tablero_asesores_pg import URL, pytestmark, sesion  # noqa: F401


MARZO = ["2097-03"]


async def _filtro(db, meses=MARZO, modo=t.HMCL_INCLUIR, tiendas=None):
    return await q.cargar_filtro(db, meses, modo, tiendas)


def _red_de_enero(detalle):
    return next(p for p in detalle["tendencia"] if p["mes"] == "2097-01")["red_pct"]


async def test_ventas_line_and_tecnired_blocks_cover_the_window_whatever_the_period(sesion):
    await Mundo().crear(sesion)

    r = await k.calcular_kpis_ventas(sesion, await _filtro(sesion))

    assert r["ventana_meses"][-3:] == MESES
    assert r["total"]["venta"]["total"] == pytest.approx(1700)  # the rest of the tab follows the period
    assert r["meses"] == MARZO
    total = r["ventana"]["total"]
    assert sorted(total["venta"]["por_mes_linea"]) == MESES
    assert total["venta"]["total"] == pytest.approx(4900)
    assert "costo" not in total  # the window reads no inventory cost: live and summary stay identical
    assert total["venta"]["por_mes"]["2097-02"] == pytest.approx(1500)
    tecnired = r["ventana"]["tecnired"]
    assert tecnired["venta"] == pytest.approx(1300)
    assert tecnired["por_mes"]["2097-02"] == {"venta": pytest.approx(1300), "clientes": 2}
    assert r["tecnired"]["venta"] == pytest.approx(0)


async def test_ventas_window_keeps_the_store_filter_and_the_hmcl_mode(sesion):
    mundo = await Mundo().crear(sesion)

    norte = await k.calcular_kpis_ventas(sesion, await _filtro(sesion, tiendas=[mundo.norte.id]))
    solo = await k.calcular_kpis_ventas(sesion, await _filtro(sesion, modo=t.HMCL_SOLO))

    assert norte["ventana"]["total"]["venta"]["total"] == pytest.approx(4400)
    assert norte["ventana"]["total"]["venta"]["por_mes"]["2097-01"] == pytest.approx(1500)
    assert solo["ventana"]["total"]["venta"]["total"] == pytest.approx(0)  # no HMCL client in this world


async def test_ventas_window_is_the_period_when_the_period_already_covers_it(sesion):
    await Mundo().crear(sesion)

    r = await k.calcular_kpis_ventas(sesion, await _filtro(sesion, MESES))

    assert r["ventana_meses"][-3:] == MESES
    assert r["ventana"]["total"]["venta"]["total"] == r["total"]["venta"]["total"]


async def test_tiendas_heatmap_window_has_every_month_of_each_store(sesion):
    mundo = await Mundo().crear(sesion)

    r = await k.calcular_kpis_tiendas(sesion, await _filtro(sesion))

    assert r["ventana_meses"][-3:] == MESES
    por_tienda = {f["sucursal_id"]: f["venta"] for f in r["ventana"]["tiendas"]}
    norte = por_tienda[str(mundo.norte.id)]
    assert norte["total"] == pytest.approx(4400)
    assert [norte["por_mes"][m] for m in MESES] == [pytest.approx(x) for x in (1500, 1300, 1600)]
    assert {f["sucursal_id"]: f["venta"]["total"] for f in r["tiendas"]}[str(mundo.norte.id)] == pytest.approx(1600)


async def test_tiendas_window_keeps_the_store_filter(sesion):
    mundo = await Mundo().crear(sesion)

    r = await k.calcular_kpis_tiendas(sesion, await _filtro(sesion, tiendas=[mundo.sur.id]))

    assert [f["sucursal_id"] for f in r["ventana"]["tiendas"]] == [str(mundo.sur.id)]


async def test_the_asesor_trend_covers_the_window_whatever_the_period(sesion):
    mundo = await Mundo().crear(sesion)

    r = await k.calcular_kpis_asesor_detalle(sesion, await _filtro(sesion), mundo.cedulas["ana"])

    assert r["ventana_meses"][-3:] == MESES
    assert [p["mes"] for p in r["tendencia"]] == r["ventana_meses"]
    pcts = {p["mes"]: p["pct"] for p in r["tendencia"]}
    assert [pcts[m] for m in MESES] == [pytest.approx(1.0), pytest.approx(1.0), pytest.approx(0.875)]
    assert r["cumplimiento_mes"]["mes"] == "2097-03"  # the rest of the detail follows the period


async def test_the_asesor_trend_window_keeps_the_store_filter(sesion):
    mundo = await Mundo().crear(sesion)

    todas = await k.calcular_kpis_asesor_detalle(sesion, await _filtro(sesion), mundo.cedulas["ana"])
    norte = await k.calcular_kpis_asesor_detalle(
        sesion, await _filtro(sesion, tiendas=[mundo.norte.id]), mundo.cedulas["ana"])

    assert _red_de_enero(norte) == pytest.approx(1.0)  # Norte: 1500 sold of 1500 budgeted
    assert _red_de_enero(todas) == pytest.approx(1700 / 1900)
