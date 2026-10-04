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
    eco = q.eco_reglas(t.REGLAS_POR_DEFECTO, hasta)

    assert eco == {"semaforo": {"verde_desde": 90, "ambar_desde": 70},
                   "cumplimiento_base": "con_hmcl", "vigencia": esperado}


# --- reglas leidas de Configuracion: forma y tipos ---------------------------------------------


def _valores(**cambios):
    base = {
        "lineas_comerciales": ["GPS"], "hmcl_nits": ["123"],
        "grupo_por_cargo": {"X": "PERSONA"},
        "kpi_semaforo_cortes": {"verde_desde": 95, "ambar_desde": 60},
        "cumplimiento_base": "sin_hmcl",
    }
    base.update(cambios)
    return base


def test_un_grupo_desconocido_en_el_mapa_de_cargos_pasa_a_otros():
    valores = _valores(grupo_por_cargo={"A": "PERSONA", "B": "COMERCIALES", "C": "VIP'; DROP", "D": "RESTO"})

    reglas = t.reglas_desde_valores(valores)

    assert reglas.grupo_por_cargo == {"A": "PERSONA", "B": "COMERCIALES", "C": "OTROS", "D": "OTROS"}


def test_las_lineas_de_configuracion_se_normalizan_como_las_de_la_referencia():
    valores = _valores(lineas_comerciales=["  gps ", "Baterías", "CASCOS", "gps"])

    reglas = t.reglas_desde_valores(valores)

    assert reglas.lineas == ("GPS", "BATERIAS", "CASCOS")


def test_una_linea_de_configuracion_con_tildes_coincide_con_la_de_la_cte():
    reglas = t.reglas_desde_valores(_valores(lineas_comerciales=["Baterías"]))

    valores = _parametros(q._lineas_por_referencia(reglas).element)

    assert "BATERIAS" in valores and "Baterías" not in valores


@pytest.mark.parametrize("clave, malo", [
    ("lineas_comerciales", "GPS"),
    ("lineas_comerciales", [1, 2]),
    ("lineas_comerciales", []),
    ("hmcl_nits", {"a": 1}),
    ("hmcl_nits", [None]),
    ("grupo_por_cargo", ["x"]),
    ("grupo_por_cargo", {"A": 3}),
    ("kpi_semaforo_cortes", [90, 70]),
    ("kpi_semaforo_cortes", {"verde_desde": "alto", "ambar_desde": 70}),
    ("kpi_semaforo_cortes", {"verde_desde": 60, "ambar_desde": 70}),
    ("kpi_semaforo_cortes", {"verde_desde": 90}),
    ("cumplimiento_base", "otra"),
    ("cumplimiento_base", 7),
])
def test_un_valor_con_forma_invalida_vuelve_al_defecto_de_esa_clave_y_avisa(clave, malo, caplog):
    valores = _valores(**{clave: malo})

    with caplog.at_level("WARNING"):
        reglas = t.reglas_desde_valores(valores)

    defecto = t.REGLAS_POR_DEFECTO
    esperado = {
        "lineas_comerciales": ("lineas", defecto.lineas),
        "hmcl_nits": ("hmcl_nits", defecto.hmcl_nits),
        "grupo_por_cargo": ("grupo_por_cargo", defecto.grupo_por_cargo),
        "kpi_semaforo_cortes": ("semaforo", defecto.semaforo),
        "cumplimiento_base": ("cumplimiento_base", defecto.cumplimiento_base),
    }[clave]
    assert getattr(reglas, esperado[0]) == esperado[1]
    assert clave in caplog.text
    # Las demas claves siguen con lo configurado.
    if clave != "lineas_comerciales":
        assert reglas.lineas == ("GPS",)


def test_un_semaforo_numerico_se_conserva_como_numeros():
    reglas = t.reglas_desde_valores(_valores(kpi_semaforo_cortes={"verde_desde": "95", "ambar_desde": 60.5}))

    assert reglas.semaforo == {"verde_desde": 95.0, "ambar_desde": 60.5}
