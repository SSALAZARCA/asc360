"""
KPI margin with the real ERP sale cost (`venta_detalle.costo`) against a real Postgres
(opt-in, database migrated to head).

A mixed world (lines with a real cost, with a cost whose sign disagrees with the quantity,
returns with and without cost, a line of a referencia that has no fallback at all, plain
lines on the unit fallback) is rebuilt into the summaries. The summary equals the Python
expectation written from the rule, and every summary read equals its live query, for the
margin cube and for the cost that feeds the days of inventory. Every test rolls back.
"""
from decimal import Decimal as D

from app.motored.services import kpi_resumen as k
from app.motored.services import kpi_resumen_lectura as lectura
from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_asesores_consultas as q
from app.motored.services import tablero_kpis_consultas as qk
from tests.motored.pg_real.test_kpi_resumen_lectura_pg import _llave_cubo
from tests.motored.pg_real.test_kpi_resumen_pg import (  # noqa: F401
    Mundo, _ids, _leer, pytestmark, sesion,
)

MESES = ["2097-01", "2097-02", "2097-03"]


async def _mundo_mixto(db):
    mundo = await Mundo().crear(db)
    for fila in [
        # (suc, ref, vend, cli, mes, dia, nro, cant, bruto, desc, origen, carga, costo)
        (mundo.s1, "R1", "ANA", "Taller X", 2, 20, "N1", 2, 1000, 0, "MOSTRADOR", mundo.c_venta, "380"),
        (mundo.s1, "R1", "ANA", "Taller X", 2, 21, "N2", -1, -500, 0, "MOSTRADOR", mundo.c_venta, "200"),
        (mundo.s1, "R2", "ANA", "Taller X", 2, 22, "N3", -2, -300, 0, "MOSTRADOR", mundo.c_venta, None),
        (mundo.s1, "R3", "BETO", "Taller X", 2, 23, "N4", 3, 900, 0, "MOSTRADOR", mundo.c_venta, "-270"),
        (mundo.s1, "R4", "ANA", "Taller X", 3, 20, "N5", 1, 700, 0, "MOSTRADOR", mundo.c_venta, "120"),
        (mundo.s2, "R5", "CARLA", "Taller Y", 3, 21, "N6", 2, 600, 0, "VENTA", mundo.c_venta, "90"),
        (mundo.s2, "R1", "ANA", "Taller Y", 3, 22, "N7", 0, 50, 0, "VENTA", mundo.c_venta, "55"),
        (mundo.s2, "R1", "ANA", "Taller Y", 3, 23, "N8", 4, 400, 0, "VENTA", mundo.c_venta, "0"),
    ]:
        await mundo.linea(db, *fila)
    await db.flush()
    await k.reconstruir_todo(db)
    return mundo


async def test_the_summary_prices_each_line_with_the_rule(sesion):
    mundo = await _mundo_mixto(sesion)

    assert await _leer(sesion, _ids(mundo)) == mundo.esperado()


async def test_the_live_cube_and_the_cost_of_sales_equal_the_summary(sesion):
    mundo = await _mundo_mixto(sesion)
    corte = await q.fecha_corte_costos(sesion)
    for tiendas in (None, [mundo.s1.id]):
        filtro = await q.cargar_filtro(sesion, MESES, t.HMCL_INCLUIR, tiendas)
        for dimension in (t.DIM_ASESOR, t.DIM_SUCURSAL):
            vivo = await q.consultar_cubo(sesion, filtro, corte, dimension)
            resumen = await lectura.cubo_resumen(sesion, filtro, dimension)
            assert sorted(resumen, key=_llave_cubo) == sorted(vivo, key=_llave_cubo), dimension
        assert await lectura.costo_venta_resumen(sesion, filtro) == await qk.consultar_costo_venta(
            sesion, filtro, corte)


async def test_the_live_cost_matches_the_python_expectation(sesion):
    mundo = await _mundo_mixto(sesion)
    corte = await q.fecha_corte_costos(sesion)
    filtro = await q.cargar_filtro(sesion, MESES, t.HMCL_INCLUIR, None)
    venta, _firmas, _clientes = mundo.esperado()

    vivo = await q.consultar_cubo(sesion, filtro, corte, t.DIM_SUCURSAL)

    assert sum((f.costo for f in vivo), D(0)) == sum((v[5] for v in venta.values()), D(0))
    assert sum((f.costo_estimado for f in vivo), D(0)) == sum((v[6] for v in venta.values()), D(0))


async def test_refreshing_a_month_equals_the_full_rebuild(sesion):
    mundo = await _mundo_mixto(sesion)
    completo = await _leer(sesion, _ids(mundo))

    await k.refrescar_periodos(sesion, {(mundo.s1.id, 2097, 2), (mundo.s2.id, 2097, 3)})

    assert await _leer(sesion, _ids(mundo)) == completo
