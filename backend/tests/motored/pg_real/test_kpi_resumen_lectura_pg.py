"""
KPI summary read path for `kpi_venta_mes` (odd/motored-kpis-resumenes, R3) against a
real Postgres (opt-in, database migrated to head).

The acceptance criterion: for the same Filtro, the summary reads return EXACTLY what
the live queries return. A world of two stores and three months (vendors mapped,
unmapped, inactive and with two ERP names for one cedula; recognized, accented and
unrecognized lines; HMCL / Tecnired / plain / blank clients; an ANULADO carga;
inventory with and without cost and the `precio_normal` fallback) is built once,
the summaries are rebuilt, and every comparison runs for contiguous and
non-contiguous months, with and without the store filter, in each HMCL mode, under the
default Configuracion and under Configuracion rows that change lines, HMCL NITs and the
cargo groups. Every test rolls back.
"""
import datetime
import uuid
from collections import defaultdict
from decimal import Decimal as D
from itertools import product

import pytest
from sqlalchemy import delete, select

from app.config import settings
from app.motored.models.kpi_resumen import KpiResumenEstado, KpiVentaMes
from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.models.vendedor import Vendedor
from app.motored.services import kpi_resumen as k
from app.motored.services import kpi_resumen_lectura as lectura
from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_asesores_consultas as q
from app.motored.services import tablero_kpis as kpis
from app.motored.services import tablero_kpis_consultas as qk
from tests.motored.pg_real.test_kpi_resumen_pg import URL, Mundo, pytestmark, sesion  # noqa: F401

REPUESTOS_CARGO, COMERCIAL, TALLER = "ASESOR DE REPUESTOS", "ASESOR COMERCIAL DE SERVICIO POSVENTA", "JEFE DE TALLER"
MESES = {"todo": ["2097-01", "2097-02", "2097-03"], "salteado": ["2097-01", "2097-03"], "uno": ["2097-02"],
         "ultimo": ["2097-03"]}


async def _mundo(db, configuracion):
    mundo = await Mundo().crear(db)
    cedula = str(uuid.uuid4().int)[:10]

    def vend(nombre, cargo, ced, suc, activo=True):
        return Vendedor(id=uuid.uuid4(), nombre=nombre, nombre_norm=nombre, cargo=cargo, cedula=ced,
                        sucursal_id=suc.id if suc else None, activo=activo)

    db.add_all([
        vend("ANA", REPUESTOS_CARGO, cedula, mundo.s1), vend("BETO", REPUESTOS_CARGO, cedula, mundo.s2),
        vend("CARLA", COMERCIAL, None, None), vend("LUIS", TALLER, str(uuid.uuid4().int)[:10], mundo.s1),
        vend("INACTIVO", REPUESTOS_CARGO, None, mundo.s1, activo=False),
    ])
    for fila in [
        (mundo.s1, "R2", "LUIS", "Taller X", 2, 11, "L1", 2, 400, 40, "MOSTRADOR", mundo.c_venta),
        (mundo.s2, "R3", "INACTIVO", mundo.tec, 3, 12, "I1", 1, 700, 0, "VENTA", mundo.c_mar),
        (mundo.s2, "R1", "BETO", "   ", 3, 13, "B2", 1, 90, 0, "VENTA", mundo.c_mar),
        (mundo.s1, "R7", "CARLA", "900723988", 3, 14, "C3", 2, 300, 30, "VENTA", mundo.c_mar),
    ]:
        await mundo.linea(db, *fila)
    if configuracion:
        desde = datetime.date(2097, 2, 1)
        for clave, valor in (
            ("lineas_comerciales", ["Repuestos", "ACCESORIOS", "motos", "Baterías"]),
            ("hmcl_nits", [mundo.tec, "900883086"]),
            ("grupo_por_cargo", {REPUESTOS_CARGO: t.TIPO_PERSONA, TALLER: t.GRUPO_COMERCIALES}),
        ):
            db.add(ParametroMetodologia(id=uuid.uuid4(), clave=clave, valor=valor, vigente_desde=desde))
    await db.flush()
    await k.reconstruir_todo(db)
    return mundo


def _llave_cubo(f):
    return (f.clave, f.mes, f.linea or "", f.es_hmcl, f.es_tecnired, f.es_mostrador, f.con_costo)


def _plegar_total(filas):
    """Folds a cube to one row per (mes, linea, flags): the TOTAL dimension."""
    acc = defaultdict(lambda: [D(0)] * 6 + [0])
    for f in filas:
        a = acc[(f.mes, f.linea, f.es_hmcl, f.es_tecnired, f.es_mostrador, f.con_costo)]
        for i, v in enumerate((f.venta, f.bruto, f.descuentos, f.cantidad, f.costo, f.costo_estimado)):
            a[i] += v
        a[6] += f.lineas
    return sorted(((*llave, *v) for llave, v in acc.items()), key=lambda r: (r[0], r[1] or "", r[2:6]))


def _filtros(sesion_, mundo):
    return [
        (nombre, modo, tiendas, (sesion_, meses, modo, tiendas))
        for (nombre, meses), modo, tiendas in product(
            MESES.items(), (t.HMCL_INCLUIR, t.HMCL_EXCLUIR, t.HMCL_SOLO), (None, [mundo.s1.id]))
    ]


@pytest.mark.parametrize("configuracion", [False, True], ids=["default-config", "changed-config"])
async def test_every_summary_read_equals_its_live_query(sesion, configuracion):
    mundo = await _mundo(sesion, configuracion)
    corte = await q.fecha_corte_costos(sesion)
    assert await lectura.meses_resumen(sesion) == await q.meses_disponibles(sesion)

    for nombre, modo, tiendas, args in _filtros(sesion, mundo):
        donde = f"{nombre}/{modo}/{'s1' if tiendas else 'todas'}/{'config' if configuracion else 'default'}"
        filtro = await q.cargar_filtro(sesion, args[1], modo, tiendas)
        for dimension in (t.DIM_ASESOR, t.DIM_SUCURSAL):
            vivo = await q.consultar_cubo(sesion, filtro, corte, dimension)
            assert vivo, donde
            resumen = await lectura.cubo_resumen(sesion, filtro, dimension)
            assert sorted(resumen, key=_llave_cubo) == sorted(vivo, key=_llave_cubo), (donde, dimension)
        vivo_sucursal = await q.consultar_cubo(sesion, filtro, corte, t.DIM_SUCURSAL)
        total = await lectura.cubo_resumen(sesion, filtro, t.DIM_TOTAL)
        assert {f.clave for f in total} <= {t.CLAVE_TOTAL}
        assert _plegar_total(total) == _plegar_total(vivo_sucursal), donde

        for ventana in (filtro, kpis.filtro_de_ventana(filtro)):
            for dimension in (t.DIM_ASESOR, t.DIM_SUCURSAL):
                en_vivo = await q.consultar_ventana_mensual(sesion, ventana, dimension)
                en_resumen = await lectura.ventana_mensual_resumen(sesion, ventana, dimension)
                assert sorted(en_resumen) == sorted(en_vivo), (donde, dimension)

        assert await lectura.costo_venta_resumen(sesion, filtro) == await qk.consultar_costo_venta(
            sesion, filtro, corte), donde
        personas_vivo = await q.consultar_personas(sesion, filtro)
        personas_resumen = await lectura.personas_resumen(sesion, filtro)
        assert sorted(personas_resumen, key=lambda p: p.clave) == sorted(personas_vivo, key=lambda p: p.clave), donde


async def test_the_world_exercises_what_the_equivalence_has_to_cover(sesion):
    mundo = await _mundo(sesion, True)
    corte = await q.fecha_corte_costos(sesion)
    filtro = await q.cargar_filtro(sesion, MESES["todo"], t.HMCL_INCLUIR, [mundo.s1.id, mundo.s2.id])

    cubo = await lectura.cubo_resumen(sesion, filtro, t.DIM_ASESOR)

    assert any(f.es_hmcl for f in cubo) and any(f.es_tecnired for f in cubo)
    assert any(f.linea is None for f in cubo) and any(not f.con_costo for f in cubo)
    assert any(f.costo_estimado > 0 for f in cubo) and any(f.es_mostrador for f in cubo)
    assert {t.GRUPO_RESTO, t.GRUPO_COMERCIALES} <= {f.clave for f in cubo}
    assert len({f.clave for f in cubo if f.clave.startswith(t.PREFIJO_PERSONA)}) >= 1
    assert corte is not None


@pytest.mark.parametrize("configuracion", [False, True], ids=["default-config", "changed-config"])
async def test_the_dashboards_are_identical_with_the_switch_on_and_off(sesion, monkeypatch, configuracion):
    mundo = await _mundo(sesion, configuracion)
    ids = [mundo.s1.id, mundo.s2.id]
    filtro = await q.cargar_filtro(sesion, MESES["todo"], t.HMCL_EXCLUIR, ids)
    llamadas = {
        "tablero": lambda: q.calcular_tablero(sesion, "2097-01", "2097-03", t.HMCL_INCLUIR, sucursal_ids=ids),
        "asesores": lambda: kpis.calcular_kpis_asesores(sesion, filtro),
        "tiendas": lambda: kpis.calcular_kpis_tiendas(sesion, filtro),
        "ventas": lambda: kpis.calcular_kpis_ventas(sesion, filtro),
        "opciones": lambda: kpis.calcular_opciones(sesion),
    }

    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", False)
    en_vivo = {nombre: await llamar() for nombre, llamar in llamadas.items()}
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", True)
    assert await lectura.usar_resumen(sesion)
    desde_resumen = {nombre: await llamar() for nombre, llamar in llamadas.items()}

    assert desde_resumen == en_vivo


async def test_the_switch_needs_the_setting_and_clean_built_summaries(sesion, monkeypatch):
    await Mundo().crear(sesion)
    await sesion.execute(delete(KpiResumenEstado))
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", True)
    assert await lectura.usar_resumen(sesion) is False  # no state row: never built

    await k.marcar_sucio(sesion)
    assert await lectura.usar_resumen(sesion) is False  # dirty and never rebuilt

    await k.reconstruir_todo(sesion)
    assert await lectura.usar_resumen(sesion) is True

    await k.marcar_sucio(sesion)
    assert await lectura.usar_resumen(sesion) is False  # a change is pending a full rebuild

    await k.reconstruir_todo(sesion)
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", False)
    assert await lectura.usar_resumen(sesion) is False  # switched off


async def test_the_dispatch_reads_the_summary_only_when_usable(sesion, monkeypatch):
    mundo = await Mundo().crear(sesion)
    await k.reconstruir_todo(sesion)
    filtro = await q.cargar_filtro(sesion, MESES["todo"], t.HMCL_INCLUIR, [mundo.s1.id])
    await sesion.execute(delete(KpiVentaMes).where(KpiVentaMes.sucursal_id == mundo.s1.id))  # a recognizable tamper

    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", True)
    assert await lectura.cubo(sesion, filtro, None, t.DIM_SUCURSAL) == []
    assert await lectura.meses(sesion) == await lectura.meses_resumen(sesion)
    await k.marcar_sucio(sesion)
    assert await lectura.cubo(sesion, filtro, None, t.DIM_SUCURSAL) == await q.consultar_cubo(
        sesion, filtro, None, t.DIM_SUCURSAL)
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", False)
    assert await lectura.personas(sesion, filtro) == await q.consultar_personas(sesion, filtro)
    assert await lectura.ventana_mensual(sesion, filtro, t.DIM_SUCURSAL) == await q.consultar_ventana_mensual(
        sesion, filtro, t.DIM_SUCURSAL)
    assert await lectura.costo_venta(sesion, filtro, None) == await qk.consultar_costo_venta(sesion, filtro, None)
