"""
Inventario KPI summary tables against a real Postgres (opt-in): what the builder stores.

World of `test_tablero_kpis_inventario_pg` (year 2096; cortes Aug 31, Sep 30, Oct 7 and an annulled Oct 20)
plus a second Oct corte (Oct 2) that must NOT be kept: only the latest corte of each month is a closing cut.
"""
from decimal import Decimal as D

from sqlalchemy import select

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.kpi_resumen import KpiCostoMesReferencia, KpiInventarioCorte, KpiInventarioPar
from app.motored.services import kpi_resumen as k
from tests.motored.pg_real.test_kpi_inventario_resumen_world import mundo_con_resumen
from tests.motored.pg_real.test_tablero_asesores_pg import pytestmark, sesion  # noqa: F401
from tests.motored.pg_real.test_tablero_kpis_inventario_pg import C_AGO, C_OCT, C_SEP, F, _linea_costo


async def _pares(db):
    filas = (await db.execute(select(KpiInventarioPar))).scalars().all()
    return {(f.fecha_corte, f.sucursal_id, f.referencia_id): (f.existencia, f.valor) for f in filas}


async def test_only_the_closing_cut_of_each_month_is_kept_for_the_summary_tables(sesion):
    await mundo_con_resumen(sesion)

    cortes = {f.fecha_corte for f in (await sesion.execute(select(KpiInventarioCorte))).scalars().all()}
    pares = await _pares(sesion)

    assert cortes == {C_AGO, C_SEP, C_OCT}  # not the annulled Oct 20 nor the earlier Oct 2
    assert {clave[0] for clave in pares} == cortes


async def test_a_pair_sums_the_bodegas_and_values_each_line_with_the_live_rule(sesion):
    w = await mundo_con_resumen(sesion)

    pares = await _pares(sesion)

    r1, r5, r2 = (w.refs[c].id for c in ("R1", "R5", "R2"))
    assert pares[(C_OCT, w.s["S1"].id, r1)] == (D(15), D(2500))   # 10 x 100 + 5 x 300 (two bodegas)
    assert pares[(C_OCT, w.s["S3"].id, r1)] == (D(5), D(500))     # the associated store keeps its own row
    assert pares[(C_OCT, w.s["S1"].id, r5)] == (D(6), D(120))     # no cost: precio_normal 20
    assert pares[(C_OCT, w.s["S2"].id, r2)] == (D(0), D(0))       # zero stock is stored too


async def test_the_closing_cut_values_per_store_follow_the_live_valuation(sesion):
    w = await mundo_con_resumen(sesion)

    filas = (await sesion.execute(select(KpiInventarioCorte))).scalars().all()
    valores = {(f.fecha_corte, f.sucursal_id): f.valor for f in filas}

    assert valores[(C_OCT, w.s["S1"].id)] == D(3030) and valores[(C_OCT, w.s["S3"].id)] == D(500)
    assert valores[(C_AGO, w.s["S1"].id)] == D(800) and valores[(C_AGO, w.s["S2"].id)] == D(2000)
    assert valores[(C_SEP, w.s["S1"].id)] == D(900) and valores[(C_SEP, w.s["S2"].id)] == D(3000)


async def test_the_cost_of_sales_is_stored_per_month_store_and_referencia(sesion):
    w = await mundo_con_resumen(sesion)

    filas = (await sesion.execute(select(KpiCostoMesReferencia))).scalars().all()
    costos = {(f.anio_mes, f.sucursal_id, f.referencia_id): f.costo for f in filas}

    r1 = w.refs["R1"].id
    assert costos[(F(2096, 8, 1), w.s["S1"].id, r1)] == D(600)
    assert costos[(F(2096, 7, 1), w.s["S1"].id, r1)] == D(5000)
    assert costos[(F(2096, 9, 1), w.s["S3"].id, r1)] == D(300)    # raw store: the rollup is read time
    assert costos[(F(2096, 10, 1), w.s["S2"].id, r1)] == D(400)   # HMCL client: the cost keeps it


async def test_an_applied_ventas_carga_refreshes_the_cost_rows_of_its_months(sesion):
    w = await mundo_con_resumen(sesion)
    carga = (await sesion.execute(select(CargaArchivo).where(CargaArchivo.tipo == "VENTAS"))).scalars().first()
    r1 = w.refs["R1"].id

    _linea_costo(sesion, w, carga, "S1", "R1", 2096, 8, 50)
    await sesion.flush()
    await k.refrescar_periodos(sesion, {(w.s["S1"].id, 2096, 8)})

    fila = (await sesion.execute(select(KpiCostoMesReferencia).where(
        KpiCostoMesReferencia.anio_mes == F(2096, 8, 1), KpiCostoMesReferencia.sucursal_id == w.s["S1"].id,
        KpiCostoMesReferencia.referencia_id == r1))).scalar_one()
    assert fila.costo == D(650)


async def test_reconstruir_costos_reprices_the_cost_rows(sesion):
    await mundo_con_resumen(sesion)
    antes = (await sesion.execute(select(KpiCostoMesReferencia))).scalars().all()

    await k.reconstruir_costos(sesion)
    despues = (await sesion.execute(select(KpiCostoMesReferencia))).scalars().all()

    assert len(despues) == len(antes) > 0
