"""
KPI's, pestana Inventario, served from the summary tables (opt-in Postgres): the whole payload must be
IDENTICAL with the summaries on and off, fall back to live when they are dirty, follow a rebuild, and not scan
the big raw tables (`venta_detalle`, `inventario_detalle`) when they answer.

The world is the one of `test_tablero_kpis_inventario_pg` (cortes, stores incl. an associated one, lines, lost
sales, transit, annulled loads, pairs without sales) with the summaries fully built.
"""
import datetime
import uuid
from decimal import Decimal as D

import pytest
from sqlalchemy import event, select

from app.config import settings
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.inventario_detalle import InventarioDetalle
from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.services import kpi_resumen as k
from app.motored.services import tablero_kpis_inventario_consultas as qi
from app.motored.services import kpi_resumen_lectura as lectura
from app.motored.services import tablero_kpis as kpis
from tests.motored.pg_real.test_kpi_inventario_resumen_world import mundo_con_resumen
from tests.motored.pg_real.test_kpi_resumen_lectura_pg import sin_frescura
from tests.motored.pg_real.test_tablero_asesores_pg import pytestmark, sesion  # noqa: F401
from tests.motored.pg_real.test_tablero_kpis_inventario_pg import _filtro, _linea_costo

TIENDAS = {
    "todas": ("S1", "S2", "S4"), "principal": ("S1",), "otra": ("S2",), "sin-inventario": ("S4",),
    "asociada": ("S3",), "ninguna": (),
}


async def _datos(db, monkeypatch, w, activo, tiendas, **filtro):
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", activo)
    with lectura.memo_de_peticion(db):
        f = await _filtro(db, w, tiendas=tiendas, **filtro)
        return await kpis.calcular_kpis_inventario(db, f)


@pytest.mark.parametrize("tiendas", list(TIENDAS), ids=list(TIENDAS))
async def test_the_payload_is_identical_with_the_summaries_on_and_off(sesion, monkeypatch, tiendas):
    w = await mundo_con_resumen(sesion)

    en_vivo = await _datos(sesion, monkeypatch, w, False, TIENDAS[tiendas])
    desde_resumen = await _datos(sesion, monkeypatch, w, True, TIENDAS[tiendas])

    assert (en_vivo["usando_resumen"], desde_resumen["usando_resumen"]) == (False, True)
    assert desde_resumen["datos_actualizados_en"] and en_vivo["datos_actualizados_en"] is None
    assert sin_frescura(desde_resumen) == sin_frescura(en_vivo)
    if TIENDAS[tiendas] != ("S4",):
        assert en_vivo["corte"] == "2096-10-07" and en_vivo["tendencia"] and en_vivo["tarjetas"]["valor"] > 0


async def test_the_excel_lists_are_identical_with_the_summaries_on_and_off(sesion, monkeypatch):
    w = await mundo_con_resumen(sesion)
    salida = {}
    for activo in (False, True):
        monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", activo)
        with lectura.memo_de_peticion(sesion):
            datos, sin_mov, agotadas = await kpis.calcular_kpis_inventario_completo(
                sesion, await _filtro(sesion, w))
        salida[activo] = (sin_frescura(datos), sin_mov, agotadas)

    assert salida[True] == salida[False]
    assert salida[True][1] and salida[True][2]


async def test_a_changed_line_configuration_gives_the_same_payload(sesion, monkeypatch):
    w = await mundo_con_resumen(sesion)
    sesion.add(ParametroMetodologia(
        id=uuid.uuid4(), clave="lineas_comerciales", valor=["Repuestos", "ACCESORIOS", "baterías"],
        vigente_desde=datetime.date(2090, 1, 1)))
    await sesion.flush()
    await k.reconstruir_todo(sesion)

    en_vivo = await _datos(sesion, monkeypatch, w, False, TIENDAS["todas"])
    desde_resumen = await _datos(sesion, monkeypatch, w, True, TIENDAS["todas"])

    assert desde_resumen["usando_resumen"] is True
    assert sin_frescura(desde_resumen) == sin_frescura(en_vivo)
    assert {x["linea"] for x in en_vivo["lineas"]} - {"Sin línea"} <= {"REPUESTOS", "ACCESORIOS", "BATERIAS"}


async def test_a_dirty_summary_falls_back_to_live_and_says_so(sesion, monkeypatch):
    w = await mundo_con_resumen(sesion)
    await k.marcar_sucio(sesion)

    sucio = await _datos(sesion, monkeypatch, w, True, TIENDAS["todas"])
    apagado = await _datos(sesion, monkeypatch, w, False, TIENDAS["todas"])

    assert sucio["usando_resumen"] is False and sucio["datos_actualizados_en"] is None
    assert sin_frescura(sucio) == sin_frescura(apagado)


async def test_a_rebuild_after_an_inventory_load_shows_the_new_corte(sesion, monkeypatch):
    w = await mundo_con_resumen(sesion)
    carga = (await sesion.execute(select(CargaArchivo).where(
        CargaArchivo.tipo == "INVENTARIO", CargaArchivo.estado == "APLICADO"))).scalars().first()
    sesion.add(InventarioDetalle(
        id=uuid.uuid4(), carga_id=carga.id, fecha_corte=datetime.date(2096, 11, 5), sucursal_id=w.s["S1"].id,
        referencia_id=w.refs["R3"].id, bodega="B1", existencia=D(3), costo_unitario=D(10)))
    await sesion.flush()
    assert await k.marcar_sucio_si_construido(sesion)

    sucio = await _datos(sesion, monkeypatch, w, True, TIENDAS["todas"])
    await k.reconstruir_todo(sesion)
    reconstruido = await _datos(sesion, monkeypatch, w, True, TIENDAS["todas"])
    en_vivo = await _datos(sesion, monkeypatch, w, False, TIENDAS["todas"])

    assert sucio["usando_resumen"] is False and sucio["corte"] == "2096-11-05"
    assert reconstruido["usando_resumen"] is True and reconstruido["corte"] == "2096-11-05"
    assert sin_frescura(reconstruido) == sin_frescura(en_vivo) == sin_frescura(sucio)


async def test_a_sales_load_refreshes_the_cost_of_sales_the_tab_reads_without_a_rebuild(sesion, monkeypatch):
    w = await mundo_con_resumen(sesion)
    carga = (await sesion.execute(select(CargaArchivo).where(
        CargaArchivo.tipo == "VENTAS", CargaArchivo.estado == "APLICADO"))).scalars().first()
    antes = await _datos(sesion, monkeypatch, w, True, TIENDAS["todas"])
    _linea_costo(sesion, w, carga, "S1", "R1", 2096, 10, 4000)
    await sesion.flush()
    assert await k.refrescar_si_construido(sesion, {(w.s["S1"].id, 2096, 10)})

    desde_resumen = await _datos(sesion, monkeypatch, w, True, TIENDAS["todas"])
    en_vivo = await _datos(sesion, monkeypatch, w, False, TIENDAS["todas"])

    assert desde_resumen["usando_resumen"] is True
    assert sin_frescura(desde_resumen) == sin_frescura(en_vivo)
    assert desde_resumen["tarjetas"]["dias"] != antes["tarjetas"]["dias"]


async def _sentencias(db, monkeypatch, w, activo):
    sentencias = []
    motor = db.bind.sync_engine

    def escuchar(conexion, cursor, sentencia, *args):
        sentencias.append(sentencia)

    event.listen(motor, "before_cursor_execute", escuchar)
    try:
        await _datos(db, monkeypatch, w, activo, TIENDAS["todas"])
    finally:
        event.remove(motor, "before_cursor_execute", escuchar)
    return sentencias


async def test_with_the_summaries_the_big_raw_tables_are_not_read_and_fewer_queries_run(sesion, monkeypatch):
    w = await mundo_con_resumen(sesion)

    en_vivo = await _sentencias(sesion, monkeypatch, w, False)
    resumen = await _sentencias(sesion, monkeypatch, w, True)

    grandes = ("FROM venta_detalle", "FROM inventario_detalle", "JOIN venta_detalle", "JOIN inventario_detalle")
    assert any(g in s for s in en_vivo for g in grandes)
    assert not [s for s in resumen for g in grandes if g in s]
    assert len(en_vivo) <= 25 and len(resumen) <= len(en_vivo) + 1  # +1: the state of the summaries
    assert len(resumen) <= 24, f"{len(resumen)} queries with the summaries on"


# --- each reader against its live query ----------------------------------------------------------------


@pytest.mark.parametrize("tiendas", ["todas", "principal", "asociada", "ninguna"])
async def test_every_summary_reader_equals_its_live_query(sesion, tiendas):
    w = await mundo_con_resumen(sesion)
    filtro = await _filtro(sesion, w, tiendas=TIENDAS[tiendas])
    cortes = await qi.consultar_cortes(sesion)
    cierres = [c for c in cortes if c != datetime.date(2096, 10, 2)]
    corte = max(cortes)

    assert await lectura.cortes_resumen(sesion) == cierres
    assert await lectura.valor_por_corte_resumen(sesion, filtro, cierres) == await qi.consultar_valor_por_corte(
        sesion, filtro, cierres)
    vivos = await qi.consultar_costos_por_mes(sesion, filtro, corte, "2096-06", "2096-10")
    assert sorted(await lectura.costos_por_mes_resumen(sesion, filtro, corte, "2096-06", "2096-10")) == sorted(vivos)
    assert vivos
    pares_vivos = await qi.consultar_pares_con_existencia(sesion, filtro, corte)
    por_corte_vivo = await qi.consultar_pares_por_corte(sesion, filtro, cierres)
    pares, por_corte = lectura.separar_pares(await lectura.pares_resumen(sesion, filtro, cierres), corte, cierres)
    assert sorted(pares, key=str) == sorted(pares_vivos, key=str)
    assert {c: sorted(f, key=str) for c, f in por_corte.items()} == {
        c: sorted(f, key=str) for c, f in por_corte_vivo.items()}
