"""
KPI's (B3) contra un Postgres real (opt-in): cubo por sucursal, ventana de
crecimiento con meses no contiguos y clasificacion `nueva` por `fecha_apertura`.
Reusa el mundo de `test_tablero_asesores_pg` (anio 2098).

Venta por tienda y mes (solo lineas reconocidas, todas las personas): Cali Norte
(s1) 01 -> 2300, 02 -> 810, 03 -> 1100, 04 -> 540, 06 -> 910; Bogota (s2) 05 -> 300.
"""
import datetime

import pytest
from sqlalchemy import select

from app.motored.models.sucursal import Sucursal
from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_asesores_consultas as q
from app.motored.services import tablero_kpis as k
from tests.motored.pg_real.test_tablero_asesores_pg import (  # noqa: F401
    URL, _mundo, pytestmark, sesion,
)

TODOS = [f"2098-0{m}" for m in range(1, 7)]


async def _tiendas(db, meses, modo="incluir", sucursales=None):
    filtro = await q.cargar_filtro(db, meses, modo, sucursales)
    return await k.calcular_kpis_tiendas(db, filtro)


def _tienda(resultado, nombre, sfx):
    return next(f for f in resultado["tiendas"] if f["nombre"] == f"{nombre} {sfx}")


async def test_el_cubo_por_sucursal_trae_toda_la_venta_de_cada_tienda(sesion):
    sfx, _ = await _mundo(sesion)

    r = await _tiendas(sesion, TODOS)

    cali, bogota = _tienda(r, "Cali Norte", sfx), _tienda(r, "Bogota", sfx)
    assert cali["venta"]["total"] == 5660.0 and bogota["venta"]["total"] == 300.0  # includes RESTO (Dora, Eva)
    assert [f["nombre"] for f in r["tiendas"]] == [f"Cali Norte {sfx}", f"Bogota {sfx}"]
    assert cali["venta"]["por_mes"]["2098-01"] == 2300.0 and bogota["venta"]["por_mes"]["2098-05"] == 300.0
    assert cali["venta"]["por_mes_linea"]["2098-01"]["REPUESTOS"] == 1800.0
    assert cali["venta"]["por_mes_linea"]["2098-01"]["ACCESORIOS"] == 500.0
    assert cali["clientes"]["tecnired_por_mes"]["2098-06"] == 810.0
    assert cali["clientes"]["tecnired_por_linea"]["LLANTAS"] == 810.0
    assert bogota["facturas"]["facturas"] == 1 and bogota["clientes"]["clientes_unicos"] == 1
    assert r["venta_sin_linea"] == 5800.0  # E1 (no commercial line) 5000 + A4 (NO APLICA) 800


async def test_la_red_cuadra_con_el_tablero_de_asesores_y_con_la_suma_de_las_tiendas(sesion):
    await _mundo(sesion)
    filtro = await q.cargar_filtro(sesion, TODOS, "incluir")

    ventas = await k.calcular_kpis_ventas(sesion, filtro)
    tablero = await q.calcular_tablero_por_meses(sesion, TODOS, "incluir")
    tiendas = await k.calcular_kpis_tiendas(sesion, filtro)

    total = ventas["total"]
    assert total["venta"]["total"] == tablero["total"]["venta"]["total"] == 5960.0
    assert total["venta"]["por_mes_linea"] == tablero["total"]["venta"]["por_mes_linea"]
    assert total["clientes"]["tecnired_por_mes"] == tablero["total"]["clientes"]["tecnired_por_mes"]
    assert total["facturas"] == tablero["total"]["facturas"]
    assert total["clientes"]["clientes_unicos"] == tablero["total"]["clientes"]["clientes_unicos"]
    assert sum(f["facturas"]["facturas"] for f in tiendas["tiendas"]) == total["facturas"]["facturas"]
    assert sum(f["venta"]["total"] for f in ventas["tiendas"]) == 5960.0
    assert set(ventas["tiendas"][0]) == {"sucursal_id", "nombre", "venta", "costo"}
    assert ventas["venta_sin_linea"] == tablero["venta_sin_linea"]


async def test_el_crecimiento_ignora_los_meses_elegidos_y_usa_la_ventana_de_calendario(sesion):
    sfx, _ = await _mundo(sesion)

    contiguo = await _tiendas(sesion, ["2098-05", "2098-06"])
    salteado = await _tiendas(sesion, ["2098-02", "2098-05", "2098-06"])

    for r in (contiguo, salteado):
        cali, bogota = _tienda(r, "Cali Norte", sfx), _tienda(r, "Bogota", sfx)
        # 04+05+06 = 540 + 0 + 910 against 01+02+03 = 2300 + 810 + 1100.
        assert (cali["crecimiento"]["ultimos_3m"], cali["crecimiento"]["previos_3m"]) == (1450.0, 4210.0)
        assert cali["crecimiento"]["pct"] == pytest.approx(1450 / 4210 - 1)
        assert cali["crecimiento"]["clasificacion"] == t.CAE
        assert bogota["crecimiento"]["clasificacion"] == t.NUEVA  # nothing sold in 01..03
    assert _tienda(contiguo, "Cali Norte", sfx)["venta"]["total"] == 910.0
    # The sales shown are only the selected months; the growth above is not.
    assert _tienda(salteado, "Cali Norte", sfx)["venta"]["total"] == 810.0 + 910.0
    assert contiguo["resumen_crecimiento"] == salteado["resumen_crecimiento"] == {t.CRECE: 0, t.CAE: 1, t.NUEVA: 1}


async def test_el_crecimiento_cruza_el_anio_y_clasifica_una_tienda_que_crece(sesion):
    sfx, _ = await _mundo(sesion)

    r = await _tiendas(sesion, ["2098-04"])  # window 2097-11..2098-04

    cali = _tienda(r, "Cali Norte", sfx)
    assert (cali["crecimiento"]["ultimos_3m"], cali["crecimiento"]["previos_3m"]) == (2450.0, 2300.0)
    assert cali["crecimiento"]["clasificacion"] == t.CRECE
    assert r["resumen_crecimiento"][t.CRECE] == 1


async def test_la_fecha_de_apertura_dentro_de_la_ventana_clasifica_nueva(sesion):
    sfx, _ = await _mundo(sesion)
    cali = (await sesion.execute(select(Sucursal).where(Sucursal.nombre == f"Cali Norte {sfx}"))).scalar_one()

    cali.fecha_apertura = datetime.date(2098, 1, 1)
    await sesion.flush()
    nueva = _tienda(await _tiendas(sesion, ["2098-06"]), "Cali Norte", sfx)
    cali.fecha_apertura = datetime.date(2097, 12, 31)
    await sesion.flush()
    vieja = _tienda(await _tiendas(sesion, ["2098-06"]), "Cali Norte", sfx)

    assert nueva["crecimiento"]["clasificacion"] == t.NUEVA
    assert vieja["crecimiento"]["clasificacion"] == t.CAE


async def test_la_ventana_respeta_el_filtro_de_sucursal_y_el_modo_hmcl(sesion):
    sfx, _ = await _mundo(sesion)
    s2 = (await sesion.execute(select(Sucursal.id).where(Sucursal.nombre == f"Bogota {sfx}"))).scalar_one()

    solo_s2 = await _tiendas(sesion, ["2098-05"], sucursales=[s2])
    sin_hmcl = await _tiendas(sesion, ["2098-02"], modo="excluir")

    assert [f["nombre"] for f in solo_s2["tiendas"]] == [f"Bogota {sfx}"]
    assert solo_s2["tiendas"][0]["crecimiento"]["ultimos_3m"] == 300.0
    cali = _tienda(sin_hmcl, "Cali Norte", sfx)
    # Ana's HMCL line of 02 (360) and Dora's HMCL line of 01 (900) leave out of the window too.
    assert cali["venta"]["total"] == 450.0
    assert cali["crecimiento"]["ultimos_3m"] == (500.0 + 900.0) + 450.0
