"""
KPI summary read path for invoices and clients (odd/motored-kpis-resumenes, R4) against a
real Postgres (opt-in, database migrated to head).

The acceptance criterion: for the same Filtro, the summary reads return EXACTLY what the
live queries return. The world of the R3 equivalence test is extended with the invoices that
break a naive "one summary row per invoice" grain: multi-line invoices, one invoice whose
lines belong to two vendors of the same person, one that spans two months, one that mixes a
plain, an HMCL and a Tecnired client, a blank client, and lines that are only recognized
under a changed Configuracion. Every comparison runs for contiguous and non-contiguous
months, with and without the store filter, in each HMCL mode, under the default Configuracion
and under rows that change lines, HMCL NITs and the cargo groups. Every test rolls back.
"""
import uuid
from itertools import product

import pytest
from sqlalchemy import delete, select

from app.config import settings
from app.motored.models.cliente_tecnired import ClienteTecnired
from app.motored.models.kpi_resumen import KpiClienteMes, KpiFacturaFirma
from app.motored.services import kpi_resumen as k
from app.motored.services import kpi_resumen_lectura as lectura
from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_asesores_consultas as q
from app.motored.services import tablero_kpis as kpis
from app.motored.services import tablero_kpis_consultas as qk
from tests.motored.pg_real.test_kpi_resumen_lectura_pg import MESES, _mundo, sin_frescura
from tests.motored.pg_real.test_kpi_resumen_pg import pytestmark, sesion  # noqa: F401

DIMENSIONES = (t.DIM_ASESOR, t.DIM_SUCURSAL, t.DIM_TOTAL)


async def _mundo_con_facturas(db, configuracion):
    mundo = await _mundo(db, configuracion)
    for fila in [
        # ML1: three lines of three different lines, one vendor
        (mundo.s1, "R1", "ANA", "Taller X", 2, 20, "ML1", 1, 100, 0, "VENTA", mundo.c_venta),
        (mundo.s1, "R2", "ANA", "Taller X", 2, 20, "ML1", 1, 200, 0, "VENTA", mundo.c_venta),
        (mundo.s1, "R3", "ANA", "Taller X", 2, 20, "ML1", 1, 300, 0, "VENTA", mundo.c_venta),
        # ML2: two ERP names of the same person (the same asesor row)
        (mundo.s1, "R1", "ANA", "Taller X", 2, 21, "ML2", 1, 110, 0, "VENTA", mundo.c_venta),
        (mundo.s1, "R2", "BETO", "Taller X", 2, 21, "ML2", 1, 120, 0, "VENTA", mundo.c_venta),
        # ML3: an invoice that spans two months
        (mundo.s1, "R1", "ANA", "Taller X", 1, 28, "ML3", 1, 130, 0, "VENTA", mundo.c_venta),
        (mundo.s1, "R2", "ANA", "Taller X", 2, 1, "ML3", 1, 140, 0, "VENTA", mundo.c_venta),
        # ML4: a plain client and a Tecnired / HMCL client on the same invoice
        (mundo.s1, "R1", "ANA", "Taller X", 3, 20, "ML4", 1, 150, 0, "VENTA", mundo.c_mar),
        (mundo.s1, "R3", "ANA", mundo.tec, 3, 20, "ML4", 1, 160, 0, "VENTA", mundo.c_mar),
        # ML5: a blank client on a multi-line invoice
        (mundo.s2, "R1", "ANA", "  ", 2, 22, "ML5", 1, 170, 0, "VENTA", mundo.c_venta),
        (mundo.s2, "R2", "ANA", "  ", 2, 22, "ML5", 1, 180, 0, "VENTA", mundo.c_venta),
        # ML6: a line that is only recognized under the changed Configuracion, and an unrecognized one
        (mundo.s2, "R1", "ANA", "Taller X", 3, 23, "ML6", 1, 190, 0, "VENTA", mundo.c_mar),
        (mundo.s2, "R7", "ANA", "Taller X", 3, 23, "ML6", 1, 200, 0, "VENTA", mundo.c_mar),
        (mundo.s2, "R4", "ANA", "Taller X", 3, 23, "ML6", 1, 210, 0, "VENTA", mundo.c_mar),
        # ML7: two vendors that are different rows of the tablero
        (mundo.s1, "R1", "CARLA", "Taller X", 2, 24, "ML7", 1, 220, 0, "VENTA", mundo.c_venta),
        (mundo.s1, "R5", "LUIS", "Taller X", 2, 24, "ML7", 1, 230, 0, "VENTA", mundo.c_venta),
        # A second Tecnired client with a razon social, bigger than the first
        (mundo.s2, "R1", "ANA", "811999888", 2, 25, "ML8", 1, 9000, 0, "VENTA", mundo.c_venta),
    ]:
        await mundo.linea(db, *fila)
    db.add(ClienteTecnired(id=uuid.uuid4(), nit="811999888", razon_social="Tecni Dos"))
    await db.flush()
    await k.reconstruir_todo(db)
    return mundo


def _filtros(mundo):
    return [
        (f"{nombre}/{modo}/{'s1' if tiendas else 'todas'}", meses, modo, tiendas)
        for (nombre, meses), modo, tiendas in product(
            MESES.items(), (t.HMCL_INCLUIR, t.HMCL_EXCLUIR, t.HMCL_SOLO), (None, [mundo.s1.id]))
    ]


async def _tablero(db, filtro):
    tablero, cubo = await q.tablero_de_filtro(db, filtro)
    return tablero, sorted(cubo, key=lambda f: (f.clave, f.mes, f.linea or "", f.es_hmcl, f.es_tecnired,
                                                f.es_mostrador, f.con_costo))


def _clave(fila):
    return fila.clave


@pytest.mark.parametrize("configuracion", [False, True], ids=["default-config", "changed-config"])
async def test_invoices_and_clients_from_the_summary_equal_the_live_queries(sesion, configuracion):
    mundo = await _mundo_con_facturas(sesion, configuracion)
    comparadas = 0

    for nombre, meses, modo, tiendas in _filtros(mundo):
        donde = f"{nombre}/{'config' if configuracion else 'default'}"
        filtro = await q.cargar_filtro(sesion, meses, modo, tiendas)
        for dimension in DIMENSIONES:
            facturas_vivo = await q.consultar_facturas(sesion, filtro, dimension=dimension)
            facturas = await lectura.facturas_resumen(sesion, filtro, dimension=dimension)
            assert sorted(facturas, key=_clave) == sorted(facturas_vivo, key=_clave), (donde, dimension, "facturas")
            clientes_vivo = await q.consultar_clientes(sesion, filtro, dimension=dimension)
            clientes = await lectura.clientes_resumen(sesion, filtro, dimension=dimension)
            assert sorted(clientes, key=_clave) == sorted(clientes_vivo, key=_clave), (donde, dimension, "clientes")
            comparadas += bool(facturas_vivo) + bool(clientes_vivo)

        assert await lectura.clientes_tecnired_resumen(sesion, filtro) == await qk.consultar_clientes_tecnired(
            sesion, filtro), donde
        assert await lectura.top_tecnired_resumen(sesion, filtro) == await qk.consultar_top_tecnired(
            sesion, filtro), donde
        assert await lectura.top_tecnired_resumen(sesion, filtro, 1) == await qk.consultar_top_tecnired(
            sesion, filtro, 1), donde
    assert comparadas > 100  # the matrix is not comparing empty answers


async def test_the_world_exercises_the_invoice_shapes_that_break_the_naive_grain(sesion):
    await _mundo_con_facturas(sesion, False)
    todas = await q.cargar_filtro(sesion, MESES["todo"], t.HMCL_INCLUIR, None)

    facturas = {f.clave: f for f in await q.consultar_facturas(sesion, todas, dimension=t.DIM_TOTAL)}
    asesores = {f.clave: f for f in await q.consultar_facturas(sesion, todas, dimension=t.DIM_ASESOR)}
    filas = (await sesion.execute(select(KpiFacturaFirma.firma, KpiFacturaFirma.vendedor_norm))).all()

    assert facturas[t.CLAVE_TOTAL].multilinea >= 4
    assert len(asesores) >= 3
    assert any(len(firma) > 1 for firma, _ in filas) and any(not firma for firma, _ in filas)
    assert any(firma and "|" in firma[0] for firma, _ in filas)  # the invoices the plain grain cannot hold
    assert len(await lectura.top_tecnired_resumen(sesion, todas)) == 2


@pytest.mark.parametrize("configuracion", [False, True], ids=["default-config", "changed-config"])
async def test_the_dashboards_are_identical_with_the_switch_on_and_off(sesion, monkeypatch, configuracion):
    mundo = await _mundo_con_facturas(sesion, configuracion)
    ids = [mundo.s1.id, mundo.s2.id]
    llamadas = {}
    for modo in (t.HMCL_INCLUIR, t.HMCL_EXCLUIR, t.HMCL_SOLO):
        for nombre, meses in MESES.items():
            filtro = await q.cargar_filtro(sesion, meses, modo, ids if nombre != "uno" else [mundo.s1.id])
            llamadas.update({
                (modo, nombre, "tablero"): lambda f=filtro: _tablero(sesion, f),
                (modo, nombre, "asesores"): lambda f=filtro: kpis.calcular_kpis_asesores(sesion, f),
                (modo, nombre, "tiendas"): lambda f=filtro: kpis.calcular_kpis_tiendas(sesion, f),
                (modo, nombre, "ventas"): lambda f=filtro: kpis.calcular_kpis_ventas(sesion, f),
            })

    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", False)
    en_vivo = {nombre: sin_frescura(await llamar()) for nombre, llamar in llamadas.items()}
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", True)
    assert await lectura.usar_resumen(sesion)
    desde_resumen = {nombre: sin_frescura(await llamar()) for nombre, llamar in llamadas.items()}

    assert desde_resumen == en_vivo


async def test_the_comparison_detects_a_summary_that_drifted(sesion):
    mundo = await _mundo_con_facturas(sesion, False)
    filtro = await q.cargar_filtro(sesion, MESES["todo"], t.HMCL_INCLUIR, [mundo.s1.id])
    antes = await lectura.facturas_resumen(sesion, filtro, dimension=t.DIM_TOTAL)
    clientes_antes = await lectura.clientes_resumen(sesion, filtro, dimension=t.DIM_TOTAL)

    await sesion.execute(
        KpiFacturaFirma.__table__.update().where(KpiFacturaFirma.sucursal_id == mundo.s1.id).values(n_facturas=7))
    await sesion.execute(KpiClienteMes.__table__.delete().where(KpiClienteMes.sucursal_id == mundo.s1.id))

    vivo = await q.consultar_facturas(sesion, filtro, dimension=t.DIM_TOTAL)
    assert await lectura.facturas_resumen(sesion, filtro, dimension=t.DIM_TOTAL) != vivo
    assert await lectura.clientes_resumen(sesion, filtro, dimension=t.DIM_TOTAL) != clientes_antes
    assert antes == vivo


async def test_a_refreshed_period_keeps_the_multi_month_invoices_exact(sesion):
    mundo = await _mundo_con_facturas(sesion, False)
    # A line added to ML3 (Jan 28 / Feb 1) in Feb only: refreshing Feb must also fix the January part.
    await mundo.linea(sesion, mundo.s1, "R3", "BETO", "Taller X", 2, 2, "ML3", 1, 50, 0, "VENTA", mundo.c_venta)
    await sesion.flush()

    await k.refrescar_periodos(sesion, {(mundo.s1.id, 2097, 2)})

    for meses in (MESES["todo"], MESES["uno"], ["2097-01"]):
        filtro = await q.cargar_filtro(sesion, meses, t.HMCL_INCLUIR, None)
        for dimension in DIMENSIONES:
            vivo = await q.consultar_facturas(sesion, filtro, dimension=dimension)
            assert sorted(await lectura.facturas_resumen(sesion, filtro, dimension=dimension), key=_clave) == sorted(
                vivo, key=_clave), (meses, dimension)


async def test_the_dispatch_reads_the_summary_only_when_usable(sesion, monkeypatch):
    mundo = await _mundo_con_facturas(sesion, False)
    filtro = await q.cargar_filtro(sesion, MESES["todo"], t.HMCL_INCLUIR, [mundo.s1.id])
    await sesion.execute(delete(KpiClienteMes).where(KpiClienteMes.sucursal_id == mundo.s1.id))  # a recognizable tamper
    await sesion.execute(delete(KpiFacturaFirma).where(KpiFacturaFirma.sucursal_id == mundo.s1.id))

    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", True)
    assert await lectura.clientes(sesion, filtro, dimension=t.DIM_SUCURSAL) == []
    assert await lectura.facturas(sesion, filtro, dimension=t.DIM_SUCURSAL) == []
    assert await lectura.clientes_tecnired(sesion, filtro) == (0, {})
    assert await lectura.top_tecnired(sesion, filtro) == []

    await k.marcar_sucio(sesion)  # a pending rebuild: back to the live queries
    assert await lectura.clientes(sesion, filtro, dimension=t.DIM_SUCURSAL) == await q.consultar_clientes(
        sesion, filtro, dimension=t.DIM_SUCURSAL)
    assert await lectura.facturas(sesion, filtro, dimension=t.DIM_SUCURSAL) == await q.consultar_facturas(
        sesion, filtro, dimension=t.DIM_SUCURSAL)
    assert await lectura.clientes_tecnired(sesion, filtro) == await qk.consultar_clientes_tecnired(sesion, filtro)
    assert await lectura.top_tecnired(sesion, filtro) == await qk.consultar_top_tecnired(sesion, filtro)


async def test_an_invoice_with_a_null_key_is_never_dropped_from_the_firma_table(sesion):
    from sqlalchemy import Date, Text, cast, func, literal, null

    # The grain flag must be null-safe: with NULL keys `min = max` is NULL, which is neither
    # "simple" nor "irregular", so the invoice would vanish from both shapes.
    nulos = select(
        cast(null(), Date).label("anio_mes"), cast(null(), Text).label("vendedor_norm"),
        cast(null(), Text).label("nit"), literal("A").label("grupo")).subquery()
    bandera = k._es_simple(nulos.c.anio_mes, nulos.c.vendedor_norm, nulos.c.nit)
    assert (await sesion.execute(select(bandera).group_by(nulos.c.grupo))).scalar_one() is True


async def test_pipes_inside_the_invoice_tokens_do_not_change_the_split(sesion):
    mundo = await _mundo_con_facturas(sesion, False)
    # An irregular invoice (two months) whose vendedor and special NIT both contain the delimiter.
    sesion.add(ClienteTecnired(id=uuid.uuid4(), nit="900|1", razon_social="Pipe SAS"))
    await mundo.linea(sesion, mundo.s1, "R1", "ZOE|PIPE", "900|1", 1, 29, "MLP", 1, 10, 0, "VENTA", mundo.c_venta)
    await mundo.linea(sesion, mundo.s1, "R2", "ZOE|PIPE", "900|1", 2, 3, "MLP", 1, 20, 0, "VENTA", mundo.c_venta)
    await sesion.flush()
    await k.reconstruir_todo(sesion)

    for meses in MESES.values():
        for modo in (t.HMCL_INCLUIR, t.HMCL_EXCLUIR, t.HMCL_SOLO):
            filtro = await q.cargar_filtro(sesion, meses, modo, None)
            for dimension in DIMENSIONES:
                vivo = await q.consultar_facturas(sesion, filtro, dimension=dimension)
                assert sorted(await lectura.facturas_resumen(sesion, filtro, dimension=dimension),
                              key=_clave) == sorted(vivo, key=_clave), (meses, modo, dimension)
    tokens = (await sesion.execute(
        select(KpiFacturaFirma.firma).where(KpiFacturaFirma.nit_especial == k.NIT_FACTURA_IRREGULAR))).scalars().all()
    assert any("ZOE|PIPE" in marca and "900" + k.ESCAPE_DELIMITADOR + "1" in marca for firma in tokens for marca in firma)
