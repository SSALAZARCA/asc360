"""
Associated stores in the KPI's (odd/motored-kpis-resumenes, R9) against a real Postgres
(opt-in, database migrated to head).

An associated store (`sucursal.principal_id`) rolls into its principal for everything the
KPI's show: sales, invoices, clients, the growth window, inventory, cost of sales, budgets and
the vendedor's point of sale. Only principals are listed or filtered; selecting a principal
includes its associates. The roll-up happens at READ time on the raw `sucursal_id`, in the live
queries and in the summaries alike, so the world is built and summarized FIRST and the relation
is set afterwards: a relation change needs no rebuild.
Every test rolls back.
"""
import datetime
import uuid
from collections import defaultdict
from decimal import Decimal as D
from itertools import product

import pytest
from sqlalchemy import select

from app.config import settings
from app.motored.models.presupuesto import PresupuestoLinea, PresupuestoVersion
from app.motored.models.vendedor import Vendedor
from app.motored.schemas.vendedor import limpiar_cedula
from app.motored.services import kpi_resumen_lectura as lectura
from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_asesores_consultas as q
from app.motored.services import tablero_kpis as kpis
from app.motored.services import tablero_kpis_consultas as qk
from tests.motored.pg_real.test_kpi_resumen_facturas_clientes_pg import _mundo_con_facturas
from tests.motored.pg_real.test_kpi_resumen_lectura_pg import MESES, _llave_cubo, sin_frescura
from tests.motored.pg_real.test_kpi_resumen_pg import pytestmark, sesion  # noqa: F401

DIMENSIONES = (t.DIM_ASESOR, t.DIM_SUCURSAL, t.DIM_TOTAL)


async def _mundo_asociado(db):
    """The R4 world (two stores; sales, invoices, clients, inventory on both) summarized
    BEFORE `s2` is associated to `s1`, plus budgets of two asesores assigned to `s2`."""
    mundo = await _mundo_con_facturas(db, False)
    cedulas = {
        nombre: limpiar_cedula(cedula) for nombre, cedula in (await db.execute(
            select(Vendedor.nombre, Vendedor.cedula).where(Vendedor.nombre.in_(["ANA", "LUIS"])))).all()}
    for mes in (1, 2):
        version = PresupuestoVersion(id=uuid.uuid4(), mes=datetime.date(2097, mes, 1), version=1, origen="MANUAL")
        db.add(version)
        await db.flush()
        db.add_all([
            PresupuestoLinea(id=uuid.uuid4(), version_id=version.id, cedula=cedulas["ANA"],
                             sucursal_id=mundo.s2.id, monto=1000),
            PresupuestoLinea(id=uuid.uuid4(), version_id=version.id, cedula=cedulas["LUIS"],
                             sucursal_id=mundo.s1.id, monto=500),
        ])
    await db.flush()
    mundo.s2.principal_id = mundo.s1.id
    await db.flush()
    return mundo


def _filtros(mundo):
    return [
        (f"{nombre}/{modo}/{'s1' if tiendas else 'todas'}", meses, modo, tiendas)
        for (nombre, meses), modo, tiendas in product(
            MESES.items(), (t.HMCL_INCLUIR, t.HMCL_EXCLUIR, t.HMCL_SOLO), (None, [mundo.s1.id]))
    ]


def _clave(fila):
    return fila.clave


async def test_the_associated_store_never_appears_as_its_own_row(sesion):
    mundo = await _mundo_asociado(sesion)
    filtro = await q.cargar_filtro(sesion, MESES["todo"], t.HMCL_INCLUIR, None)
    corte = await q.fecha_corte_costos(sesion)
    s1, s2 = str(mundo.s1.id), str(mundo.s2.id)

    for nombre, lectura_ in (("live", None), ("summary", lectura)):
        if lectura_ is None:
            cubo = await q.consultar_cubo(sesion, filtro, corte, t.DIM_SUCURSAL)
            facturas = await q.consultar_facturas(sesion, filtro, dimension=t.DIM_SUCURSAL)
            clientes = await q.consultar_clientes(sesion, filtro, dimension=t.DIM_SUCURSAL)
            ventana = await q.consultar_ventana_mensual(sesion, filtro, t.DIM_SUCURSAL)
            costo, _ = await qk.consultar_costo_venta(sesion, filtro, corte)
            inventario = await qk.consultar_inventario(sesion, filtro, corte)
        else:
            cubo = await lectura.cubo_resumen(sesion, filtro, t.DIM_SUCURSAL)
            facturas = await lectura.facturas_resumen(sesion, filtro, dimension=t.DIM_SUCURSAL)
            clientes = await lectura.clientes_resumen(sesion, filtro, dimension=t.DIM_SUCURSAL)
            ventana = await lectura.ventana_mensual_resumen(sesion, filtro, t.DIM_SUCURSAL)
            costo, _ = await lectura.costo_venta_resumen(sesion, filtro)
            inventario = await lectura.inventario_resumen(sesion, filtro, corte)
        assert {f.clave for f in cubo} == {s1}, nombre
        assert {f.clave for f in facturas} == {s1} and {f.clave for f in clientes} == {s1}, nombre
        assert {f.clave for f in ventana} == {s1} and set(costo) == {s1}, nombre
        assert [f.sucursal_id for f in inventario] == [s1], nombre
        assert s2 not in {f.clave for f in cubo}


async def test_the_principal_total_is_the_sum_of_both_stores(sesion):
    mundo = await _mundo_asociado(sesion)
    corte = await q.fecha_corte_costos(sesion)
    todas = await q.cargar_filtro(sesion, MESES["todo"], t.HMCL_INCLUIR, None)
    por_asesor = sum(f.venta for f in await q.consultar_cubo(sesion, todas, corte, t.DIM_ASESOR))
    rodado_venta = defaultdict(D)
    for f in await q.consultar_cubo(sesion, todas, corte, t.DIM_SUCURSAL):
        rodado_venta[f.clave] += f.venta

    assert dict(rodado_venta) == {str(mundo.s1.id): por_asesor}
    # What each raw store sold, read without the roll-up (the relation removed again).
    mundo.s2.principal_id = None
    await sesion.flush()
    crudo = defaultdict(D)
    for f in await q.consultar_cubo(sesion, todas, corte, t.DIM_SUCURSAL):
        crudo[f.clave] += f.venta
    assert set(crudo) == {str(mundo.s1.id), str(mundo.s2.id)} and sum(crudo.values()) == por_asesor
    inventario = {f.sucursal_id: f.valor for f in await qk.consultar_inventario(sesion, todas, corte)}
    mundo.s2.principal_id = mundo.s1.id
    await sesion.flush()
    rodado = {f.sucursal_id: f.valor for f in await qk.consultar_inventario(sesion, todas, corte)}
    assert rodado == {str(mundo.s1.id): sum(inventario.values())}


async def test_filtering_by_the_principal_includes_its_associated_store(sesion):
    mundo = await _mundo_asociado(sesion)
    corte = await q.fecha_corte_costos(sesion)

    todas = await q.cargar_filtro(sesion, MESES["todo"], t.HMCL_INCLUIR, None)
    de_s1 = await q.cargar_filtro(sesion, MESES["todo"], t.HMCL_INCLUIR, [mundo.s1.id])
    de_s2 = await q.cargar_filtro(sesion, MESES["todo"], t.HMCL_INCLUIR, [mundo.s2.id])

    assert await q.consultar_cubo(sesion, de_s1, corte, t.DIM_SUCURSAL) == await q.consultar_cubo(
        sesion, todas, corte, t.DIM_SUCURSAL)
    assert await qk.consultar_inventario(sesion, de_s1, corte) == await qk.consultar_inventario(sesion, todas, corte)
    # A stale filter on the associated store itself means its principal.
    assert de_s2.sucursal_ids == frozenset({mundo.s1.id})
    assert await lectura.cubo_resumen(sesion, de_s1, t.DIM_ASESOR) == await lectura.cubo_resumen(
        sesion, todas, t.DIM_ASESOR)


async def test_summary_reads_equal_live_reads_with_an_associated_store(sesion):
    mundo = await _mundo_asociado(sesion)
    corte = await q.fecha_corte_costos(sesion)
    comparadas = 0

    for nombre, meses, modo, tiendas in _filtros(mundo):
        filtro = await q.cargar_filtro(sesion, meses, modo, tiendas)
        for dimension in DIMENSIONES:
            vivo = await q.consultar_cubo(sesion, filtro, corte, dimension) if dimension != t.DIM_TOTAL else []
            if dimension != t.DIM_TOTAL:  # the live total cube is not valid SQL and nothing reads it
                assert sorted(await lectura.cubo_resumen(sesion, filtro, dimension), key=_llave_cubo) == sorted(
                    vivo, key=_llave_cubo), (nombre, dimension, "cubo")
            for ventana in (filtro, kpis.filtro_de_ventana(filtro)) if dimension != t.DIM_TOTAL else ():
                assert sorted(await lectura.ventana_mensual_resumen(sesion, ventana, dimension)) == sorted(
                    await q.consultar_ventana_mensual(sesion, ventana, dimension)), (nombre, dimension, "ventana")
            facturas = await q.consultar_facturas(sesion, filtro, dimension=dimension)
            assert sorted(await lectura.facturas_resumen(sesion, filtro, dimension=dimension), key=_clave) == sorted(
                facturas, key=_clave), (nombre, dimension, "facturas")
            clientes = await q.consultar_clientes(sesion, filtro, dimension=dimension)
            assert sorted(await lectura.clientes_resumen(sesion, filtro, dimension=dimension), key=_clave) == sorted(
                clientes, key=_clave), (nombre, dimension, "clientes")
            comparadas += bool(vivo) + bool(facturas) + bool(clientes)
        assert await lectura.costo_venta_resumen(sesion, filtro) == await qk.consultar_costo_venta(
            sesion, filtro, corte), nombre
        assert await lectura.inventario_resumen(sesion, filtro, corte) == await qk.consultar_inventario(
            sesion, filtro, corte), nombre
        assert sorted(await lectura.personas_resumen(sesion, filtro), key=_clave) == sorted(
            await q.consultar_personas(sesion, filtro), key=_clave), nombre
        assert await lectura.clientes_tecnired_resumen(sesion, filtro) == await qk.consultar_clientes_tecnired(
            sesion, filtro), nombre
    assert comparadas > 100


async def test_the_point_of_sale_of_a_vendedor_is_his_principal_store(sesion):
    mundo = await _mundo_asociado(sesion)  # BETO is mapped to s2, which is associated to s1
    filtro = await q.cargar_filtro(sesion, MESES["todo"], t.HMCL_INCLUIR, None)

    vivo = {p.clave: p for p in await q.consultar_personas(sesion, filtro)}
    resumen = {p.clave: p for p in await lectura.personas_resumen(sesion, filtro)}

    assert resumen == vivo
    puntos = {p.punto_venta for p in vivo.values() if p.punto_venta}
    assert mundo.s1.nombre in puntos and mundo.s2.nombre not in puntos


async def test_budgets_roll_into_the_principal_and_the_filter_includes_the_associated(sesion):
    mundo = await _mundo_asociado(sesion)  # ANA's budget is assigned to s2, LUIS's to s1
    s1 = str(mundo.s1.id)

    for tiendas in (None, [mundo.s1.id]):
        filtro = await q.cargar_filtro(sesion, MESES["todo"], t.HMCL_INCLUIR, tiendas)
        cumplimiento = await kpis.cargar_cumplimiento(sesion, filtro)
        filas = cumplimiento["tiendas"]
        assert [f["sucursal_id"] for f in filas] == [s1], tiendas
        assert filas[0]["presupuesto"] == 2 * (1000 + 500) and filas[0]["nombre"] == mundo.s1.nombre
        assert {a["sucursal_id"] for a in cumplimiento["asesores"] if a["sucursal_id"]} == {s1}

    otra = await q.cargar_filtro(sesion, MESES["todo"], t.HMCL_INCLUIR, [uuid.uuid4()])
    assert (await kpis.cargar_cumplimiento(sesion, otra))["tiendas"] == []


async def test_the_options_list_only_principals(sesion):
    mundo = await _mundo_asociado(sesion)

    ids = {tienda["id"] for tienda in (await kpis.calcular_opciones(sesion))["tiendas"]}

    assert str(mundo.s1.id) in ids and str(mundo.s2.id) not in ids


@pytest.mark.parametrize("modo", [t.HMCL_INCLUIR, t.HMCL_SOLO])
async def test_the_dashboards_are_identical_with_the_switch_on_and_off(sesion, monkeypatch, modo):
    mundo = await _mundo_asociado(sesion)
    for tiendas in (None, [mundo.s1.id]):
        filtro = await q.cargar_filtro(sesion, MESES["todo"], modo, tiendas)
        llamadas = {
            "asesores": lambda: kpis.calcular_kpis_asesores(sesion, filtro),
            "tiendas": lambda: kpis.calcular_kpis_tiendas(sesion, filtro),
            "ventas": lambda: kpis.calcular_kpis_ventas(sesion, filtro),
        }
        monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", False)
        en_vivo = {nombre: sin_frescura(await llamar()) for nombre, llamar in llamadas.items()}
        monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", True)
        assert await lectura.usar_resumen(sesion)
        assert {nombre: sin_frescura(await llamar()) for nombre, llamar in llamadas.items()} == en_vivo
        assert {f["sucursal_id"] for f in en_vivo["tiendas"]["tiendas"]} == {str(mundo.s1.id)}
