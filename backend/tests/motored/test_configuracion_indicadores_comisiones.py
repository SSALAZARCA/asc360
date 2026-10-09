"""
Motored "Configuración", T6 (Indicadores) and T7 (Comisiones): the real keys
registered in `GRUPO_OPERACION`, their defaults and their validation.
"""
import datetime
from fractions import Fraction

import pytest

from app.motored.services import parametros_claves as pc
from app.motored.services import tablero_asesores as tablero
from app.motored.services.corridas import codigos

T6 = ("hmcl_nits", "grupo_por_cargo", "lineas_comerciales",
      "kpi_semaforo_cortes")
T7 = ("comision_tramos", "comision_base_pago", "cumplimiento_base",
      "comision_cargos_asesor")


def _acepta(clave, valor):
    pc.validar_escritura(clave, valor)


def _rechaza(clave, valor):
    with pytest.raises(pc.ErrorParametro) as error:
        pc.validar_escritura(clave, valor)
    assert error.value.codigo == codigos.E_PARAM_VALOR_INVALIDO


# --- registration ----------------------------------------------------------

@pytest.mark.parametrize("clave", T6 + T7)
def test_key_is_a_global_non_snapshotted_operation_key(clave):
    espec = pc.REGISTRO[clave]
    assert espec.grupo == pc.GRUPO_OPERACION
    assert espec.ambito == pc.AMBITO_GLOBAL
    assert pc.es_snapshotted(clave) is False
    assert clave not in pc.claves_motor()


@pytest.mark.parametrize("clave", T6 + T7)
def test_default_passes_its_own_validation(clave):
    _acepta(clave, pc.REGISTRO[clave].default)


def test_sections_are_indicadores_and_comisiones():
    assert {pc.seccion_de(pc.REGISTRO[c]) for c in T6} == {"indicadores"}
    assert {pc.seccion_de(pc.REGISTRO[c]) for c in T7} == {"comisiones"}


def test_defaults_match_the_constants_the_tablero_uses_today():
    assert pc.REGISTRO["hmcl_nits"].default == list(tablero.HMCL_NITS)
    assert pc.REGISTRO["lineas_comerciales"].default == list(tablero.LINEAS)
    assert pc.REGISTRO["grupo_por_cargo"].default == tablero.GRUPO_POR_CARGO


def test_commission_defaults_are_the_agreed_ones():
    assert pc.REGISTRO["comision_tramos"].default == [
        {"nombre": "BASE", "desde_pct": 0, "tasa_pct": 1.0},
        {"nombre": "PRO", "desde_pct": 90, "tasa_pct": 1.5},
        {"nombre": "ELITE", "desde_pct": 105, "tasa_pct": 1.8},
    ]
    assert pc.REGISTRO["comision_base_pago"].default == "sin_hmcl"
    assert pc.REGISTRO["cumplimiento_base"].default == "con_hmcl"
    assert pc.REGISTRO["comision_cargos_asesor"].default == [
        "ASESOR DE REPUESTOS", "ASESOR DE REPUESTOS SUPERNUMERARIO", "CAJERO POSVENTA"]
    assert pc.REGISTRO["kpi_semaforo_cortes"].default == {
        "verde_desde": 90, "ambar_desde": 70}


def test_a_sucursal_value_is_rejected_for_these_global_keys():
    with pytest.raises(pc.ErrorParametro) as error:
        pc.validar_escritura("hmcl_nits", ["900"], "una-sucursal")
    assert error.value.codigo == codigos.E_PARAM_AMBITO_INVALIDO


# --- hmcl_nits -------------------------------------------------------------

def test_hmcl_nits_accepts_unique_digit_strings():
    _acepta("hmcl_nits", ["900723988", "900883086", "123"])


@pytest.mark.parametrize("valor", [
    [], ["900", "900"], ["90-1"], [900], "900", None,
])
def test_hmcl_nits_rejects_empty_duplicated_or_non_digit(valor):
    _rechaza("hmcl_nits", valor)


# --- grupo_por_cargo -------------------------------------------------------

def test_grupo_por_cargo_accepts_the_three_groups_and_an_empty_map():
    _acepta("grupo_por_cargo", {"A": "PERSONA", "B": "COMERCIALES",
                                "C": "OTROS"})
    _acepta("grupo_por_cargo", {})


@pytest.mark.parametrize("valor", [
    {"A": "RESTO"}, {"a": "OTROS"}, {" A": "OTROS"}, {"A ": "OTROS"},
    {"": "OTROS"}, {"A": None}, ["A"], None,
])
def test_grupo_por_cargo_rejects_unknown_groups_and_unnormalized_cargos(
        valor):
    _rechaza("grupo_por_cargo", valor)


# --- lineas_comerciales ----------------------------------------------------

def test_lineas_comerciales_accepts_a_text_list():
    _acepta("lineas_comerciales", ["REPUESTOS", "GPS"])


@pytest.mark.parametrize("valor", [[], [""], ["GPS", 1], "GPS", None])
def test_lineas_comerciales_rejects_empty_or_non_text(valor):
    _rechaza("lineas_comerciales", valor)


# --- kpi_semaforo_cortes ---------------------------------------------------

@pytest.mark.parametrize("valor", [
    {"verde_desde": 90, "ambar_desde": 70},
    {"verde_desde": 200, "ambar_desde": 0},
    {"verde_desde": "100.5", "ambar_desde": "99.5"},
])
def test_semaforo_accepts_values_inside_0_to_200(valor):
    _acepta("kpi_semaforo_cortes", valor)


@pytest.mark.parametrize("valor", [
    {"verde_desde": 70, "ambar_desde": 70},
    {"verde_desde": 60, "ambar_desde": 70},
    {"verde_desde": 201, "ambar_desde": 70},
    {"verde_desde": 90, "ambar_desde": -1},
    {"verde_desde": 90},
    {"verde_desde": "x", "ambar_desde": 70},
])
def test_semaforo_rejects_out_of_range_or_wrong_order(valor):
    _rechaza("kpi_semaforo_cortes", valor)


def test_semaforo_ficha_tells_the_page_its_range():
    ficha = pc.ficha(pc.REGISTRO["kpi_semaforo_cortes"])
    assert (ficha["minimo"], ficha["maximo"]) == (0, 200)
    assert ficha["campos"] == ["verde_desde", "ambar_desde"]


# --- comision_tramos -------------------------------------------------------

def _tramos(*filas):
    return [{"nombre": n, "desde_pct": d, "tasa_pct": t}
            for n, d, t in filas]


@pytest.mark.parametrize("valor", [
    _tramos(("BASE", 0, 0)),
    _tramos(("A", 0, "1.0"), ("B", 50, 2), ("C", "50.5", 3)),
])
def test_tramos_accepts_ordered_unique_named_tiers(valor):
    _acepta("comision_tramos", valor)


@pytest.mark.parametrize("valor", [
    [],
    _tramos(("A", 5, 1)),
    _tramos(("A", 0, 1), ("B", 0, 1)),
    _tramos(("A", 0, 1), ("B", 90, 1), ("C", 80, 1)),
    _tramos(("A", 0, -1)),
    _tramos(("A", 0, 1), ("A", 90, 1)),
    _tramos(("A", 0, 1), (" a ", 90, 1)),
    _tramos(("  ", 0, 1)),
])
def test_tramos_rejects_each_broken_rule(valor):
    _rechaza("comision_tramos", valor)


def test_tramos_parse_to_exact_fractions():
    convertido = pc.parsear(
        "comision_tramos", pc.REGISTRO["comision_tramos"].default)
    assert convertido[2]["desde_pct"] == Fraction(105)
    assert convertido[2]["tasa_pct"] == Fraction(9, 5)


# --- the two enums and the cargo list --------------------------------------

@pytest.mark.parametrize("clave", ["comision_base_pago", "cumplimiento_base"])
def test_base_enums_accept_only_their_two_options(clave):
    _acepta(clave, "sin_hmcl")
    _acepta(clave, "con_hmcl")
    _rechaza(clave, "solo_hmcl")
    _rechaza(clave, None)


def test_cargos_asesor_is_a_non_empty_text_list():
    _acepta("comision_cargos_asesor", ["ASESOR DE REPUESTOS"])
    _rechaza("comision_cargos_asesor", [])
    _rechaza("comision_cargos_asesor", [1])


# --- dedicated code for the "month already passed" rule --------------------

def test_past_month_for_an_engine_key_has_its_own_code_and_message():
    assert codigos.E_PARAM_VIGENCIA_PASADA == "E-PARAM-005"
    with pytest.raises(pc.ErrorParametro) as error:
        pc.normalizar_vigencia(
            "dias_entre_pedidos", datetime.date(2026, 9, 1),
            datetime.date(2026, 10, 4))
    assert error.value.codigo == "E-PARAM-005"
    assert "mes en curso" in error.value.mensaje


def test_past_month_is_fine_for_the_new_operation_keys():
    inicio = pc.normalizar_vigencia(
        "comision_tramos", datetime.date(2026, 3, 17),
        datetime.date(2026, 10, 4))
    assert inicio == datetime.date(2026, 3, 1)
