"""
Tablero de asesores: filtro por lista de meses y sucursales contra un Postgres
real (opt-in). Reusa el mundo de `test_tablero_asesores_pg` (anio 2098).

Ventas del mundo por mes (solo lineas reconocidas): 01 -> 2300 (Ana 1400 + Dora 900),
02 -> 810 (Ana 360, Luis 200, Eva 250), 03 -> 1100 (Beto 700, Fabio 400),
04 -> 540 (Carla), 05 -> 300 (Ana, sucursal 2), 06 -> 910 (Ana 810, Luis 100).
"""
import datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.motored.models.sucursal import Sucursal
from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_asesores_consultas as q
from tests.motored.pg_real.test_tablero_asesores_pg import (  # noqa: F401
    URL, _fila, _mundo, pytestmark, sesion,
)


async def _por_meses(db, meses, modo="incluir", sucursales=None):
    return await q.calcular_tablero_por_meses(db, meses, modo, sucursales)


async def _sucursal(db, prefijo, sfx):
    return (await db.execute(select(Sucursal.id).where(Sucursal.nombre == f"{prefijo} {sfx}"))).scalar_one()


async def test_meses_salteados_traen_solo_las_ventas_de_esos_meses(sesion):
    await _mundo(sesion)

    tablero = await _por_meses(sesion, ["2098-05", "2098-01"])

    assert tablero["meses"] == ["2098-01", "2098-05"]
    assert (tablero["desde"], tablero["hasta"]) == ("2098-01", "2098-05")
    ana = _fila(tablero, "Ana")
    assert ana["venta"]["total"] == 1700.0  # 1400 en enero + 300 en mayo; febrero y junio quedan fuera
    assert ana["venta"]["por_mes"] == {"2098-01": 1400.0, "2098-05": 300.0}
    assert tablero["total"]["venta"]["total"] == 2600.0  # 900 + 500 + 900 (Dora) + 300
    # Beto, Fabio (marzo) y Carla (abril) no aparecen: no hay filas de ellos.
    assert {f["clave"] for f in tablero["filas"] if f["tipo"] == "GRUPO"} == {t.GRUPO_RESTO}
    assert tablero["venta_sin_linea"] == 5000.0  # E1 de enero


async def test_meses_salteados_con_rangos_internos_consecutivos(sesion):
    await _mundo(sesion)

    tablero = await _por_meses(sesion, ["2098-02", "2098-03", "2098-06"])

    assert tablero["total"]["venta"]["total"] == 810.0 + 1100.0 + 910.0
    assert tablero["total"]["venta"]["por_mes"] == {"2098-02": 810.0, "2098-03": 1100.0, "2098-06": 910.0}


async def test_un_rango_por_desde_hasta_da_lo_mismo_que_la_lista_de_sus_meses(sesion):
    await _mundo(sesion)

    rango = await q.calcular_tablero(sesion, "2098-01", "2098-06", "incluir")
    lista = await _por_meses(sesion, [f"2098-0{m}" for m in range(1, 7)])

    assert rango == lista


async def test_la_lista_de_meses_invalida_lanza_value_error(sesion):
    with pytest.raises(ValueError):
        await _por_meses(sesion, [])


async def test_filtro_por_sucursal_de_la_venta(sesion):
    sfx, _ = await _mundo(sesion)
    s1, s2 = await _sucursal(sesion, "Cali Norte", sfx), await _sucursal(sesion, "Bogota", sfx)
    meses = [f"2098-0{m}" for m in range(1, 7)]

    solo_s2 = await _por_meses(sesion, meses, sucursales=[s2])
    solo_s1 = await _por_meses(sesion, meses, sucursales=[s1])
    ambas = await _por_meses(sesion, meses, sucursales=[s1, s2])
    sin_filtro = await _por_meses(sesion, meses)

    assert solo_s2["total"]["venta"]["total"] == 300.0  # A1 de mayo en la sucursal 2
    assert [f["nombre"].split()[0] for f in solo_s2["filas"]] == ["Ana"]
    assert solo_s2["sucursales"] == [str(s2)]
    assert solo_s1["total"]["venta"]["total"] == 5960.0 - 300.0
    assert solo_s2["total"]["facturas"]["facturas"] == 1 and solo_s2["total"]["clientes"]["clientes_unicos"] == 1
    assert ambas["total"] == sin_filtro["total"] and sin_filtro["sucursales"] == []


async def test_una_sucursal_sin_ventas_da_un_tablero_vacio(sesion):
    import uuid
    await _mundo(sesion)

    tablero = await _por_meses(sesion, ["2098-01"], sucursales=[uuid.uuid4()])

    assert tablero["filas"] == [] and tablero["total"]["venta"]["total"] == 0.0


async def test_la_sucursal_se_combina_con_meses_salteados(sesion):
    sfx, _ = await _mundo(sesion)
    s2 = await _sucursal(sesion, "Bogota", sfx)

    mayo = await _por_meses(sesion, ["2098-01", "2098-05"], sucursales=[s2])
    enero = await _por_meses(sesion, ["2098-01", "2098-02"], sucursales=[s2])

    assert mayo["total"]["venta"]["total"] == 300.0
    assert enero["total"]["venta"]["total"] == 0.0


@pytest.mark.parametrize("modo", ["solo", "excluir"])
async def test_el_modo_hmcl_en_python_iguala_al_filtro_sql_de_antes(sesion, modo):
    await _mundo(sesion)
    filtro = t.filtro_de_meses([f"2098-0{m}" for m in range(1, 7)], modo)
    cubo = await q.consultar_cubo(sesion, filtro, await q.fecha_corte_costos(sesion))
    lineas = q._lineas_por_referencia(filtro.reglas)
    en_sql = (await sesion.execute(q._desde_ventas(
        select(func.coalesce(func.sum(q._expr_venta()), 0)), filtro, lineas,
        solo_lineas_reconocidas=False))).scalar()

    en_python = sum((f.venta for f in t.filtrar_cubo_por_hmcl(cubo, modo)), Decimal(0))

    assert en_python == en_sql


async def test_hmcl_solo_y_excluir_con_meses_salteados(sesion):
    await _mundo(sesion)

    solo = await _por_meses(sesion, ["2098-01", "2098-02"], "solo")
    excluir = await _por_meses(sesion, ["2098-01", "2098-02"], "excluir")
    incluir = await _por_meses(sesion, ["2098-01", "2098-02"])

    assert solo["total"]["venta"]["total"] == 360.0 + 900.0  # A2 (feb) y D1 (enero)
    assert excluir["total"]["venta"]["hmcl"] == 0.0
    assert solo["total"]["venta"]["total"] + excluir["total"]["venta"]["total"] == incluir["total"]["venta"]["total"]
    assert solo["total"]["facturas"]["facturas"] == 2


async def test_las_reglas_son_las_del_ultimo_mes_de_la_lista(sesion):
    import uuid
    from app.motored.models.parametro_metodologia import ParametroMetodologia
    await _mundo(sesion)
    sesion.add(ParametroMetodologia(
        id=uuid.uuid4(), clave="hmcl_nits", valor=["900723988"], vigente_desde=datetime.date(2098, 5, 1)))
    await sesion.flush()

    con_mayo = await _por_meses(sesion, ["2098-01", "2098-05"])
    sin_mayo = await _por_meses(sesion, ["2098-01", "2098-04"])

    assert con_mayo["reglas"]["vigencia"] == "2098-05" and con_mayo["total"]["venta"]["hmcl"] == 0.0
    assert sin_mayo["reglas"]["vigencia"] == "2098-04" and sin_mayo["total"]["venta"]["hmcl"] == 900.0
