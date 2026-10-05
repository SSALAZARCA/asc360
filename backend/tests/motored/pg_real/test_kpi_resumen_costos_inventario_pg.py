"""
KPI summary read path for inventory and costs (odd/motored-kpis-resumenes, R5) against a
real Postgres (opt-in, database migrated to head).

The summary of the inventory cut (`kpi_inventario_corte`) and the cut date must answer
exactly what the live queries answer: inventory at cost per store (value, uncosted lines,
lines priced from the master), the days of inventory and the margin blocks. The world of the
R3 equivalence test is extended with an inventory line whose referencia is missing from the
master (no cost -> uncosted, own cost -> valued) and fractional stock. Every test rolls back.
"""
import datetime
import uuid
from decimal import Decimal as D
from itertools import product

import pytest
from sqlalchemy import delete, text

from app.config import settings
from app.motored.models.inventario_detalle import InventarioDetalle
from app.motored.models.kpi_resumen import KpiInventarioCorte
from app.motored.services import kpi_resumen as k
from app.motored.services import kpi_resumen_lectura as lectura
from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_asesores_consultas as q
from app.motored.services import tablero_kpis as kpis
from app.motored.services import tablero_kpis_consultas as qk
from tests.motored.pg_real.test_kpi_resumen_lectura_pg import MESES, _mundo
from tests.motored.pg_real.test_kpi_resumen_pg import CORTE, pytestmark, sesion  # noqa: F401


async def _inventario_huerfano(db, mundo, sucursal, costo, existencia):
    """An inventory line whose referencia is not in the master (the FK is switched off for the insert)."""
    await db.execute(text("SET LOCAL session_replication_role = replica"))
    db.add(InventarioDetalle(
        id=uuid.uuid4(), carga_id=mundo.c_inv.id, fecha_corte=CORTE, sucursal_id=sucursal.id,
        referencia_id=uuid.uuid4(), bodega="BX", existencia=D(existencia), costo_unitario=costo))
    await db.flush()
    await db.execute(text("SET LOCAL session_replication_role = origin"))


async def _mundo_inventario(db, configuracion=False):
    mundo = await _mundo(db, configuracion)
    db.add(InventarioDetalle(
        id=uuid.uuid4(), carga_id=mundo.c_inv.id, fecha_corte=CORTE, sucursal_id=mundo.s2.id,
        referencia_id=mundo.refs["R2"].id, bodega="BF", existencia=D("2.50"), costo_unitario=D("12.34")))
    await _inventario_huerfano(db, mundo, mundo.s1, D("7.50"), "4")
    await _inventario_huerfano(db, mundo, mundo.s1, None, "3")
    await _inventario_huerfano(db, mundo, mundo.s2, D("0"), "2")
    await k.reconstruir_todo(db)
    return mundo


async def test_an_inventory_line_missing_from_the_master_is_valued_or_uncosted_never_dropped(sesion):
    mundo = await _mundo_inventario(sesion)
    filtro = await q.cargar_filtro(sesion, MESES["todo"], t.HMCL_INCLUIR, None)

    filas = {f.sucursal_id: f for f in await qk.consultar_inventario(sesion, filtro, CORTE)}

    # s1: 550 of the base world + 4 x 7.50 for the orphan line; the orphan without cost is uncosted
    assert filas[str(mundo.s1.id)].valor == D("580.00") and filas[str(mundo.s1.id)].sin_costo == 2
    # s2: 245 + 2.5 x 12.34; the orphan with cost 0 is uncosted
    assert filas[str(mundo.s2.id)].valor == D("275.85") and filas[str(mundo.s2.id)].sin_costo == 1


@pytest.mark.parametrize("configuracion", [False, True], ids=["default-config", "changed-config"])
async def test_the_inventory_summary_equals_the_live_query(sesion, configuracion):
    mundo = await _mundo_inventario(sesion, configuracion)

    for tiendas, modo in product((None, [mundo.s1.id], [mundo.s2.id]), (t.HMCL_INCLUIR, t.HMCL_SOLO)):
        filtro = await q.cargar_filtro(sesion, MESES["todo"], modo, tiendas)
        vivo = await qk.consultar_inventario(sesion, filtro, CORTE)
        assert vivo
        assert sorted(await lectura.inventario_resumen(sesion, filtro, CORTE)) == sorted(vivo)
    assert await lectura.fecha_corte_costos_resumen(sesion) == await q.fecha_corte_costos(sesion) == CORTE
    assert await lectura.inventario_resumen(sesion, filtro, None) == []


async def test_without_any_inventory_both_sources_answer_nothing(sesion):
    mundo = await _mundo_inventario(sesion)
    await sesion.execute(delete(InventarioDetalle))
    await k.reconstruir_todo(sesion)
    filtro = await q.cargar_filtro(sesion, MESES["todo"], t.HMCL_INCLUIR, [mundo.s1.id])

    assert await q.fecha_corte_costos(sesion) is None
    assert await lectura.fecha_corte_costos_resumen(sesion) is None
    assert await lectura.inventario_resumen(sesion, filtro, CORTE) == await qk.consultar_inventario(
        sesion, filtro, CORTE) == []


@pytest.mark.parametrize("configuracion", [False, True], ids=["default-config", "changed-config"])
async def test_days_of_inventory_and_margins_are_identical_with_the_switch_on_and_off(
        sesion, monkeypatch, configuracion):
    mundo = await _mundo_inventario(sesion, configuracion)
    llamadas = {}
    for nombre, meses in MESES.items():
        for tiendas in (None, [mundo.s1.id]):
            filtro = await q.cargar_filtro(sesion, meses, t.HMCL_INCLUIR, tiendas)
            clave = (nombre, bool(tiendas))
            llamadas.update({
                (*clave, "dias"): lambda f=filtro: kpis.cargar_inventario(sesion, f, CORTE),
                (*clave, "tiendas"): lambda f=filtro: kpis.calcular_kpis_tiendas(sesion, f),
                (*clave, "ventas"): lambda f=filtro: kpis.calcular_kpis_ventas(sesion, f),
                (*clave, "corte"): lambda: q.fecha_corte_costos(sesion),
            })

    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", False)
    en_vivo = {nombre: await llamar() for nombre, llamar in llamadas.items()}
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", True)
    assert await lectura.usar_resumen(sesion)
    desde_resumen = {nombre: await llamar() for nombre, llamar in llamadas.items()}

    assert desde_resumen == en_vivo
    dias = en_vivo[("todo", False, "dias")]
    assert dias["fecha_corte"] == CORTE.isoformat() and dias["tiendas"]
    margenes = en_vivo[("todo", False, "tiendas")]["tiendas"]
    assert margenes and any(f["costo"]["costo_estimado"] for f in margenes)


async def test_the_dispatch_reads_the_inventory_summary_only_when_usable(sesion, monkeypatch):
    mundo = await _mundo_inventario(sesion)
    filtro = await q.cargar_filtro(sesion, MESES["todo"], t.HMCL_INCLUIR, [mundo.s1.id])
    await sesion.execute(delete(KpiInventarioCorte).where(KpiInventarioCorte.sucursal_id == mundo.s1.id))

    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", True)
    assert await lectura.inventario(sesion, filtro, CORTE) == []  # the tampered summary answers
    await k.marcar_sucio(sesion)
    assert await lectura.inventario(sesion, filtro, CORTE) == await qk.consultar_inventario(sesion, filtro, CORTE)
    assert await lectura.fecha_corte_costos(sesion) == await q.fecha_corte_costos(sesion)
    # a cut the summary does not hold (a stale summary) falls back to the live query
    await k.reconstruir_todo(sesion)
    otro = datetime.date(2097, 12, 1)
    assert await lectura.inventario(sesion, filtro, otro) == await qk.consultar_inventario(sesion, filtro, otro)
