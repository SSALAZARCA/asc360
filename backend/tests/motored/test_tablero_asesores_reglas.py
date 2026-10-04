"""
Tablero de asesores: reglas de Configuracion (sin base de datos).

Las expresiones SQL se compilan con el dialecto de PostgreSQL para comprobar que
los valores de `Reglas` (NIT HMCL, cargos, lineas) llegan a la consulta; la
lectura real contra `parametro_metodologia` esta en `pg_real`.
"""
import datetime

import pytest
from sqlalchemy import literal
from sqlalchemy.dialects import postgresql

from app.motored.services import tablero_asesores as t
from app.motored.services import tablero_asesores_consultas as q


def _parametros(expresion):
    compilada = expresion.compile(dialect=postgresql.dialect())
    valores = []
    for v in compilada.params.values():
        valores.extend(v if isinstance(v, (list, tuple)) else [v])
    return valores


def test_el_nit_hmcl_de_las_reglas_llega_a_la_expresion():
    reglas = t.Reglas(hmcl_nits=("800999111",))

    valores = _parametros(q._expr_es_hmcl(literal("x"), reglas))

    assert "800999111" in valores and "900723988" not in valores


def test_los_cargos_de_las_reglas_llegan_a_la_clave_de_fila():
    reglas = t.Reglas(grupo_por_cargo={"JEFE DE TALLER": "PERSONA", "COORDINADOR": "COMERCIALES"})

    valores = _parametros(q._expr_clave(reglas))

    assert {"JEFE DE TALLER", "COORDINADOR"} <= set(valores)
    assert "ASESOR DE REPUESTOS" not in valores


def test_las_lineas_de_las_reglas_llegan_a_la_cte():
    reglas = t.Reglas(lineas=("GPS",))

    valores = _parametros(q._lineas_por_referencia(reglas).element)

    assert "GPS" in valores and "REPUESTOS" not in valores


async def test_cargar_reglas_arma_las_reglas_desde_leer_valores(monkeypatch):
    visto = {}

    async def falso(db, fecha, respaldos):
        visto["fecha"], visto["claves"] = fecha, set(respaldos)
        return {
            "lineas_comerciales": ["GPS"], "hmcl_nits": ["123"],
            "grupo_por_cargo": {"X": "PERSONA"},
            "kpi_semaforo_cortes": {"verde_desde": 95, "ambar_desde": 60},
            "cumplimiento_base": "sin_hmcl",
        }

    monkeypatch.setattr(q.parametros, "leer_valores", falso)

    reglas = await q.cargar_reglas(None, datetime.date(2026, 3, 31))

    assert visto["fecha"] == datetime.date(2026, 3, 31)
    assert visto["claves"] == {
        "lineas_comerciales", "hmcl_nits", "grupo_por_cargo", "kpi_semaforo_cortes", "cumplimiento_base"}
    assert reglas == t.Reglas(
        ("GPS",), ("123",), {"X": "PERSONA"}, {"verde_desde": 95, "ambar_desde": 60}, "sin_hmcl")


@pytest.mark.parametrize("hasta, esperado", [("2026-03", "2026-03"), ("2026-12", "2026-12")])
def test_el_eco_de_reglas_lleva_semaforo_base_y_vigencia(hasta, esperado):
    eco = q._eco_reglas(t.REGLAS_POR_DEFECTO, hasta)

    assert eco == {"semaforo": {"verde_desde": 90, "ambar_desde": 70},
                   "cumplimiento_base": "con_hmcl", "vigencia": esperado}
