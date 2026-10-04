"""
Tablero de asesores: reglas de Configuracion contra un Postgres real (opt-in).

Reusa el mundo de `test_tablero_asesores_pg` (anio 2098). Cada test agrega filas
de `parametro_metodologia` dentro de la transaccion (se revierte) y comprueba que
cambian los resultados; sin filas, rigen los valores por defecto del registro.
"""
import datetime
import uuid

import pytest

from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.services import tablero_asesores as t
from tests.motored.pg_real.test_tablero_asesores_pg import (  # noqa: F401
    URL, _fila, _mundo, _tablero, pytestmark, sesion,
)


def _parametro(db, clave, valor, desde=datetime.date(2098, 1, 1)):
    db.add(ParametroMetodologia(id=uuid.uuid4(), clave=clave, valor=valor, vigente_desde=desde))


async def test_sin_filas_de_configuracion_el_eco_y_los_resultados_son_los_de_siempre(sesion):
    await _mundo(sesion)

    tablero = await _tablero(sesion)

    assert tablero["reglas"] == {
        "semaforo": {"verde_desde": 90, "ambar_desde": 70},
        "cumplimiento_base": "con_hmcl", "vigencia": "2098-06"}
    assert tablero["total"]["venta"]["total"] == 5960.0 and tablero["total"]["venta"]["hmcl"] == 1260.0


async def test_hmcl_nits_vigente_en_el_mes_cambia_la_clasificacion_hmcl(sesion):
    await _mundo(sesion)
    _parametro(sesion, "hmcl_nits", ["900723988"])  # ya no es HMCL 900883086 (Dora, 900)
    await sesion.flush()

    tablero = await _tablero(sesion)

    assert tablero["total"]["venta"]["hmcl"] == 360.0
    assert _fila(tablero, clave=t.GRUPO_RESTO)["venta"]["hmcl"] == 0.0
    solo = await _tablero(sesion, "solo")
    assert solo["total"]["venta"]["total"] == 360.0


async def test_una_version_posterior_al_ultimo_mes_no_aplica(sesion):
    await _mundo(sesion)
    _parametro(sesion, "hmcl_nits", ["900723988"], desde=datetime.date(2098, 7, 1))
    await sesion.flush()

    tablero = await _tablero(sesion)

    assert tablero["total"]["venta"]["hmcl"] == 1260.0


async def test_la_version_del_ultimo_mes_manda_sobre_la_del_primero(sesion):
    await _mundo(sesion)
    _parametro(sesion, "hmcl_nits", ["900723988"], desde=datetime.date(2098, 6, 1))
    await sesion.flush()

    tablero = await _tablero(sesion, desde="2098-01", hasta="2098-06")

    assert tablero["total"]["venta"]["hmcl"] == 360.0


async def test_grupo_por_cargo_configurable_convierte_un_cargo_en_persona(sesion):
    await _mundo(sesion)
    _parametro(sesion, "grupo_por_cargo", {
        "ASESOR DE REPUESTOS": "PERSONA", "ASESOR DE REPUESTOS SUPERNUMERARIO": "PERSONA",
        "ASESOR COMERCIAL DE SERVICIO POSVENTA": "COMERCIALES", "JEFE DE TALLER": "PERSONA"})
    await sesion.flush()

    tablero = await _tablero(sesion)

    carla = _fila(tablero, "Carla")
    assert carla["tipo"] == "PERSONA" and carla["venta"]["total"] == 540.0
    assert all(f["clave"] != t.GRUPO_OTROS for f in tablero["filas"])


async def test_lineas_comerciales_reducidas_dejan_fuera_las_demas(sesion):
    await _mundo(sesion)
    _parametro(sesion, "lineas_comerciales", ["REPUESTOS", "ACCESORIOS"])
    await sesion.flush()

    tablero = await _tablero(sesion)

    ana = _fila(tablero, "Ana")
    assert list(ana["venta"]["por_linea"]) == ["REPUESTOS", "ACCESORIOS"]
    assert ana["venta"]["total"] == 2060.0  # sin LLANTAS (810)
    assert list(ana["facturas"]["pct_con_linea"]) == ["REPUESTOS", "ACCESORIOS"]


async def test_semaforo_y_base_se_leen_de_configuracion(sesion):
    await _mundo(sesion)
    _parametro(sesion, "kpi_semaforo_cortes", {"verde_desde": 95, "ambar_desde": 60})
    _parametro(sesion, "cumplimiento_base", "sin_hmcl")
    await sesion.flush()

    tablero = await _tablero(sesion)

    assert tablero["reglas"]["semaforo"] == {"verde_desde": 95, "ambar_desde": 60}
    assert tablero["reglas"]["cumplimiento_base"] == "sin_hmcl"
