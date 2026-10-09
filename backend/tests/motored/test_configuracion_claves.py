"""
Motored "Configuración" admin page, T1 (odd/motored-configuracion-admin):
the registry framework. Validators for the parameter shapes the later tasks
register (T6/T7) are proven on SYNTHETIC specs, so no real key is added here.
"""
import datetime
from fractions import Fraction

import pytest

from app.motored.services import parametros_claves as pc
from app.motored.services.corridas import codigos


def _acepta(espec, valor):
    pc.validar_espec(espec, valor)


def _rechaza(espec, valor):
    with pytest.raises(pc.ErrorParametro) as error:
        pc.validar_espec(espec, valor)
    assert error.value.codigo == codigos.E_PARAM_VALOR_INVALIDO


# --- the new group ---------------------------------------------------------

def test_operation_group_exists_and_is_not_snapshotted():
    assert pc.GRUPO_OPERACION == "OPERACION"
    assert pc.GRUPO_OPERACION != pc.GRUPO_MOTOR
    assert all(
        pc.REGISTRO[c].grupo == pc.GRUPO_MOTOR for c in pc.claves_motor())


def test_only_motor_keys_are_snapshotted():
    assert pc.es_snapshotted("dias_entre_pedidos") is True
    assert pc.es_snapshotted("dias_ventana_ingresos") is False
    assert pc.es_snapshotted("modo_tope_presupuesto") is False


# --- list of digit strings (hmcl_nits) -------------------------------------

LISTA_DIGITOS = pc.lista_de_digitos("nits_x", ["900723988"])


@pytest.mark.parametrize("valor", [["900723988"], ["1", "22"]])
def test_digit_list_accepts_digit_strings(valor):
    _acepta(LISTA_DIGITOS, valor)


@pytest.mark.parametrize("valor", [
    [], "900", ["90a"], [900], ["9 0"], [""], ["²"], None, [None],
])
def test_digit_list_rejects_everything_else(valor):
    _rechaza(LISTA_DIGITOS, valor)


def test_digit_list_lives_in_the_operation_group_by_default():
    assert LISTA_DIGITOS.grupo == pc.GRUPO_OPERACION
    assert LISTA_DIGITOS.tipo == "lista_digitos"


# --- list of text, any group -----------------------------------------------

def test_text_list_can_be_built_for_the_operation_group():
    espec = pc.lista_de_texto("cargos_x", ["A"])
    assert espec.grupo == pc.GRUPO_OPERACION
    _acepta(espec, ["ASESOR", "OTRO"])
    _rechaza(espec, [])
    _rechaza(espec, ["  "])


# --- map text -> enum (grupo_por_cargo) ------------------------------------

MAPA = pc.mapa_a_opcion(
    "mapa_x", {"GERENTE": "PERSONA"}, ("PERSONA", "COMERCIALES", "OTROS"))


@pytest.mark.parametrize("valor", [
    {}, {"GERENTE": "PERSONA"}, {"A": "OTROS", "B": "COMERCIALES"},
])
def test_enum_map_accepts_known_options(valor):
    _acepta(MAPA, valor)


@pytest.mark.parametrize("valor", [
    {"GERENTE": "RESTO"}, {"": "OTROS"}, {1: "OTROS"}, ["PERSONA"], None,
    {"A": None},
])
def test_enum_map_rejects_unknown_options_and_bad_keys(valor):
    _rechaza(MAPA, valor)


def test_enum_map_exposes_its_options_to_the_ui():
    assert MAPA.tipo == "mapa_opcion"
    assert MAPA.opciones == ("PERSONA", "COMERCIALES", "OTROS")


# --- numeric object with cross-field rule (kpi_semaforo_cortes) -------------

SEMAFORO = pc.objeto_numerico(
    "semaforo_x", {"verde_desde": 90, "ambar_desde": 70},
    ("verde_desde", "ambar_desde"), menores=(("ambar_desde", "verde_desde"),))


@pytest.mark.parametrize("valor", [
    {"verde_desde": 90, "ambar_desde": 70},
    {"verde_desde": "90.5", "ambar_desde": 0},
])
def test_numeric_object_accepts_a_valid_cross_field_pair(valor):
    _acepta(SEMAFORO, valor)


@pytest.mark.parametrize("valor", [
    {"verde_desde": 70, "ambar_desde": 70},
    {"verde_desde": 60, "ambar_desde": 70},
    {"verde_desde": 90},
    {"verde_desde": 90, "ambar_desde": 70, "extra": 1},
    {"verde_desde": 90, "ambar_desde": -1},
    {"verde_desde": "x", "ambar_desde": 70},
    {"verde_desde": True, "ambar_desde": 0},
    [90, 70], None,
])
def test_numeric_object_rejects_a_broken_object_or_cross_rule(valor):
    _rechaza(SEMAFORO, valor)


def test_numeric_object_converts_to_exact_fractions():
    valor = {"verde_desde": "90.5", "ambar_desde": 70}
    assert SEMAFORO.convertir(valor) == {
        "verde_desde": Fraction(181, 2), "ambar_desde": Fraction(70)}


def test_numeric_object_domain_names_the_cross_rule():
    assert "ambar_desde" in SEMAFORO.dominio
    assert "verde_desde" in SEMAFORO.dominio
    assert SEMAFORO.campos == ("verde_desde", "ambar_desde")


# --- ordered list of objects (comision_tramos) -----------------------------

TRAMOS_OK = [
    {"nombre": "BASE", "desde_pct": 0, "tasa_pct": "1.0"},
    {"nombre": "PRO", "desde_pct": 90, "tasa_pct": "1.5"},
    {"nombre": "ELITE", "desde_pct": "105", "tasa_pct": 1.8},
]
TRAMOS = pc.tramos_ordenados("tramos_x", TRAMOS_OK)


def _tramos(*pares):
    return [
        {"nombre": f"T{i}", "desde_pct": d, "tasa_pct": t}
        for i, (d, t) in enumerate(pares)
    ]


def test_tiers_accept_the_agreed_default():
    _acepta(TRAMOS, TRAMOS_OK)


def test_tiers_accept_a_single_tier_starting_at_zero():
    _acepta(TRAMOS, _tramos((0, 0)))


@pytest.mark.parametrize("valor", [
    [],
    _tramos((5, 1)),
    _tramos((0, 1), (0, 2)),
    _tramos((0, 1), (90, 2), (80, 3)),
    _tramos((0, -1)),
    _tramos((0, "x")),
    [{"nombre": "", "desde_pct": 0, "tasa_pct": 1}],
    [{"nombre": "A", "desde_pct": 0}],
    [{"nombre": "A", "desde_pct": 0, "tasa_pct": 1, "otro": 1}],
    ["BASE"], "BASE", None,
])
def test_tiers_reject_broken_ordering_or_fields(valor):
    _rechaza(TRAMOS, valor)


def test_tiers_convert_to_exact_fractions_keeping_the_order():
    convertido = TRAMOS.convertir(TRAMOS_OK)
    assert [t["nombre"] for t in convertido] == ["BASE", "PRO", "ELITE"]
    assert convertido[1]["desde_pct"] == Fraction(90)
    assert convertido[2]["tasa_pct"] == Fraction(9, 5)


def test_tiers_expose_their_fields():
    assert TRAMOS.tipo == "tramos"
    assert TRAMOS.campos == ("nombre", "desde_pct", "tasa_pct")


# --- ficha (what the page reads about a key) -------------------------------

def test_ficha_of_a_bounded_integer_has_its_range_and_snapshot_flag():
    ficha = pc.ficha(pc.REGISTRO["dias_entre_pedidos"])

    assert ficha["clave"] == "dias_entre_pedidos"
    assert (ficha["minimo"], ficha["maximo"]) == (1, 60)
    assert ficha["snapshotted"] is True
    assert ficha["ambito"] == pc.AMBITO_GLOBAL_Y_SUCURSAL
    assert ficha["seccion"] == "pedido"
    assert ficha["default"] == 30


def test_ficha_of_an_enum_lists_options_and_copies_the_default():
    ficha = pc.ficha(pc.REGISTRO["k_fms"])
    ficha["default"]["F"] = "999"

    assert pc.REGISTRO["k_fms"].default["F"] == "3"
    assert pc.ficha(pc.REGISTRO["modo_mes_en_curso"])["opciones"] == [
        "EXCLUIDO", "PONDERADO"]


def test_ficha_default_section_follows_the_group():
    assert pc.ficha(pc.REGISTRO["dias_ventana_ingresos"])["seccion"] == (
        "cargas")
    assert pc.ficha(pc.REGISTRO["modo_tope_presupuesto"])["seccion"] == (
        "topes")
    assert pc.ficha(pc.REGISTRO["max_dias_antiguedad_inventario"])[
        "snapshotted"] is True


def test_an_explicit_section_wins_over_the_group_default():
    espec = pc.lista_de_texto("x", ["A"], seccion="avisos")
    assert pc.ficha(espec)["seccion"] == "avisos"


def test_known_sections_are_the_eight_tabs_in_order():
    assert pc.SECCIONES == (
        "pedido", "avisos", "cargas", "limpieza", "indicadores",
        "comisiones", "conteos", "topes")


def test_every_registered_key_has_a_known_section():
    secciones = {pc.ficha(e)["seccion"] for e in pc.REGISTRO.values()}
    assert secciones <= set(pc.SECCIONES)


# --- vigencia rule ---------------------------------------------------------

HOY = datetime.date(2026, 10, 15)


def test_a_mid_month_date_is_normalized_to_the_first_of_the_month():
    assert pc.normalizar_vigencia(
        "dias_ventana_ingresos", datetime.date(2026, 11, 20), HOY,
    ) == datetime.date(2026, 11, 1)


def test_the_current_month_is_allowed_for_snapshotted_keys():
    assert pc.normalizar_vigencia(
        "dias_entre_pedidos", datetime.date(2026, 10, 3), HOY,
    ) == datetime.date(2026, 10, 1)


def test_a_past_month_is_rejected_for_snapshotted_keys_with_the_rule():
    with pytest.raises(pc.ErrorParametro) as error:
        pc.normalizar_vigencia(
            "dias_entre_pedidos", datetime.date(2026, 9, 30), HOY)

    assert error.value.codigo == codigos.E_PARAM_VIGENCIA_PASADA
    assert "dias_entre_pedidos" in error.value.mensaje
    assert "mes en curso" in error.value.mensaje
    assert "corrida" in error.value.mensaje


def test_a_past_month_is_allowed_for_non_snapshotted_keys():
    assert pc.normalizar_vigencia(
        "dias_ventana_ingresos", datetime.date(2026, 3, 9), HOY,
    ) == datetime.date(2026, 3, 1)
