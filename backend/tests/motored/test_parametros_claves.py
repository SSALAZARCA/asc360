"""
Motored Pedidos F3 "Motor", S4b (sdd/motored-pedidos-motor, ADR-7, decisión
#16): registro tipado de claves de `parametro_metodologia`.

El registro es PURO. Sólo gobierna las ESCRITURAS nuevas (`POST
/parametros`): una clave desconocida ya guardada sigue leyéndose igual
(ver `test_parametros_resolver.py`).
"""
import re
from fractions import Fraction

import pytest

from app.motored.services import parametros_claves as pc
from app.motored.services.corridas import codigos

CLAVES_F2 = {
    "tipos_inventario_incluidos": ["0002 - REPUESTOS"],
    "crear_referencias_desconocidas": False,
    "estados_backorder_vigentes": ["BACKORDER"],
    "dias_ventana_ingresos": 45,
    "tolerancia_ingreso_pct": 2.0,
}

CLAVES_ANTIGUEDAD = {
    "inventario": "max_dias_antiguedad_inventario",
    "backorder": "max_dias_antiguedad_backorder",
    "facturas": "max_dias_antiguedad_facturas",
    "ingresos": "max_dias_antiguedad_ingresos",
}

DEFAULTS_MOTOR = {
    "incluir_demanda_perdida_en_ponderada": False,
    "factor_demanda_perdida": "1",
    "consolidar_sustituidas": False,
    "dias_entre_pedidos": 30,
    "modo_mes_en_curso": "EXCLUIDO",
    "tope_proyeccion_mes_actual": "3.0",
    "min_dias_mes_actual": 5,
    "excluir_transito_vencido": False,
    "modo_redondeo_empaque": "CERCANO",
    "corte_abc_a": "0.80",
    "corte_abc_b": "0.95",
    "umbral_f": 2,
    "umbral_m": 1,
    "k_fms": {"F": "3", "M": "1.5", "S": "1"},
    "tolerancia_sobrestock": "0.25",
    "meses_inventario_muerto": 6,
}


def _codigo_de(clave, valor, sucursal_id=None):
    with pytest.raises(pc.ErrorParametro) as info:
        pc.validar_escritura(clave, valor, sucursal_id)
    return info.value.codigo


# --- Registro: claves, defaults y ámbito ---------------------------------


@pytest.mark.parametrize("clave, default", list(CLAVES_F2.items()))
def test_every_f2_ingest_key_is_registered_with_its_coded_default(
    clave, default,
):
    assert pc.REGISTRO[clave].default == default
    assert pc.REGISTRO[clave].ambito == pc.AMBITO_GLOBAL


@pytest.mark.parametrize("clave, default", list(DEFAULTS_MOTOR.items()))
def test_every_engine_key_carries_the_legacy_preset_default(clave, default):
    assert pc.REGISTRO[clave].default == default


def test_dias_entre_pedidos_is_the_only_per_sucursal_key():
    por_sucursal = {
        c for c, e in pc.REGISTRO.items()
        if e.ambito == pc.AMBITO_GLOBAL_Y_SUCURSAL
    }

    assert por_sucursal == {"dias_entre_pedidos"}


@pytest.mark.parametrize("tipo, clave", list(CLAVES_ANTIGUEDAD.items()))
def test_each_staleness_key_defaults_to_7_days_and_is_global(tipo, clave):
    assert pc.CLAVES_ANTIGUEDAD[tipo] == clave
    assert pc.REGISTRO[clave].default == 7
    assert pc.REGISTRO[clave].ambito == pc.AMBITO_GLOBAL


def test_the_superseded_single_staleness_key_is_not_registered():
    assert "dias_max_antiguedad_datos" not in pc.REGISTRO


def test_engine_group_holds_engine_and_staleness_keys_but_no_f2_key():
    motor = set(pc.claves_motor())

    assert set(DEFAULTS_MOTOR) <= motor
    assert set(CLAVES_ANTIGUEDAD.values()) <= motor
    assert motor.isdisjoint(CLAVES_F2)


# --- Validación de valores buenos ----------------------------------------


@pytest.mark.parametrize("clave, valor", [
    ("dias_entre_pedidos", 1),
    ("dias_entre_pedidos", 60),
    ("factor_demanda_perdida", 0),
    ("factor_demanda_perdida", "1.5"),
    ("modo_mes_en_curso", "PONDERADO"),
    ("modo_redondeo_empaque", "ARRIBA"),
    ("tope_proyeccion_mes_actual", 0),
    ("min_dias_mes_actual", 1),
    ("min_dias_mes_actual", 28),
    ("consolidar_sustituidas", True),
    ("max_dias_antiguedad_facturas", 15),
    ("max_dias_antiguedad_inventario", 365),
    ("k_fms", {"F": "3", "M": "1.5", "S": "1"}),
])
def test_valid_values_are_accepted(clave, valor):
    assert pc.validar_escritura(clave, valor) is None


def test_dias_entre_pedidos_accepts_a_sucursal_scope():
    sucursal = "0b9c1e0e-6a54-4a52-9a52-1f9f0a4b7c11"

    assert pc.validar_escritura("dias_entre_pedidos", 7, sucursal) is None


# --- Validación de valores malos (E-PARAM-002) ---------------------------


@pytest.mark.parametrize("valor", [0, -3, 61, 7.5, "7", None, True])
def test_dias_entre_pedidos_rejects_out_of_range_or_non_integer(valor):
    assert _codigo_de("dias_entre_pedidos", valor) == "E-PARAM-002"


@pytest.mark.parametrize("valor", [-1, "-0.5", "abc", None, True, [1]])
def test_factor_demanda_perdida_rejects_negative_or_non_numeric(valor):
    assert _codigo_de("factor_demanda_perdida", valor) == "E-PARAM-002"


@pytest.mark.parametrize("clave", [
    "consolidar_sustituidas",
    "incluir_demanda_perdida_en_ponderada",
    "excluir_transito_vencido",
    "crear_referencias_desconocidas",
])
@pytest.mark.parametrize("valor", ["true", 1, 0, None])
def test_switches_reject_non_boolean_values(clave, valor):
    assert _codigo_de(clave, valor) == "E-PARAM-002"


@pytest.mark.parametrize("clave, valor", [
    ("modo_mes_en_curso", "PROMEDIO"),
    ("modo_mes_en_curso", "ponderado"),
    ("modo_redondeo_empaque", "ABAJO"),
    ("modo_redondeo_empaque", 1),
])
def test_enum_keys_reject_values_outside_their_domain(clave, valor):
    assert _codigo_de(clave, valor) == "E-PARAM-002"


@pytest.mark.parametrize("valor", [-1, "-0.1", "x", None])
def test_tope_rejects_negative_or_non_numeric(valor):
    assert _codigo_de("tope_proyeccion_mes_actual", valor) == "E-PARAM-002"


@pytest.mark.parametrize("valor", [0, 29, -5, 5.5, "5"])
def test_min_dias_mes_actual_must_be_an_integer_between_1_and_28(valor):
    assert _codigo_de("min_dias_mes_actual", valor) == "E-PARAM-002"


@pytest.mark.parametrize("clave", list(CLAVES_ANTIGUEDAD.values()))
@pytest.mark.parametrize("valor", [0, -1, 366, 7.5, "7", None, True])
def test_staleness_keys_reject_zero_negative_or_non_integer(clave, valor):
    assert _codigo_de(clave, valor) == "E-PARAM-002"


@pytest.mark.parametrize("valor", [
    {"F": "3", "M": "1.5"},
    {"F": "3", "M": "1.5", "S": "-1"},
    {"F": "3", "M": "1.5", "S": "1", "X": "2"},
    [3, 1.5, 1],
])
def test_k_fms_needs_exactly_f_m_s_with_non_negative_numbers(valor):
    assert _codigo_de("k_fms", valor) == "E-PARAM-002"


@pytest.mark.parametrize("clave, valor", [
    ("corte_abc_a", 0),
    ("corte_abc_a", "1.2"),
    ("umbral_f", 0),
    ("meses_inventario_muerto", 7),
    ("tolerancia_sobrestock", "-0.1"),
    ("tipos_inventario_incluidos", []),
    ("tipos_inventario_incluidos", "0002 - REPUESTOS"),
    ("estados_backorder_vigentes", [1]),
    ("dias_ventana_ingresos", 0),
    ("tolerancia_ingreso_pct", -2),
])
def test_other_registered_keys_validate_their_values(clave, valor):
    assert _codigo_de(clave, valor) == "E-PARAM-002"


# --- Clave desconocida y ámbito ------------------------------------------


def test_unknown_key_is_rejected_with_e_param_001():
    assert _codigo_de("clave_que_no_existe", 1) == "E-PARAM-001"


def test_the_superseded_staleness_key_is_rejected_as_unknown():
    assert _codigo_de("dias_max_antiguedad_datos", 7) == "E-PARAM-001"


@pytest.mark.parametrize("clave, valor", [
    ("consolidar_sustituidas", True),
    ("max_dias_antiguedad_inventario", 7),
    ("dias_ventana_ingresos", 45),
])
def test_sucursal_scope_on_a_global_only_key_is_e_param_003(clave, valor):
    sucursal = "0b9c1e0e-6a54-4a52-9a52-1f9f0a4b7c11"

    assert _codigo_de(clave, valor, sucursal) == "E-PARAM-003"


def test_error_carries_a_spanish_message_naming_the_key():
    with pytest.raises(pc.ErrorParametro) as info:
        pc.validar_escritura("clave_que_no_existe", 1)

    assert "clave_que_no_existe" in info.value.mensaje
    assert info.value.codigo == codigos.E_PARAM_CLAVE_DESCONOCIDA


# --- Lectura tipada -------------------------------------------------------


def test_parsear_returns_exact_fractions_for_decimal_keys():
    assert pc.parsear("factor_demanda_perdida", "1.5") == Fraction(3, 2)
    assert pc.parsear("tope_proyeccion_mes_actual", 3) == Fraction(3)
    assert pc.parsear("corte_abc_a", "0.80") == Fraction(4, 5)


def test_parsear_returns_a_fraction_map_for_k_fms():
    assert pc.parsear("k_fms", {"F": "3", "M": "1.5", "S": "1"}) == {
        "F": Fraction(3), "M": Fraction(3, 2), "S": Fraction(1),
    }


def test_parsear_keeps_ints_bools_and_enums_as_they_are():
    assert pc.parsear("dias_entre_pedidos", 15) == 15
    assert pc.parsear("consolidar_sustituidas", True) is True
    assert pc.parsear("modo_mes_en_curso", "PONDERADO") == "PONDERADO"


def test_parsear_raises_e_param_002_for_a_stored_value_that_is_invalid():
    with pytest.raises(pc.ErrorParametro) as info:
        pc.parsear("dias_entre_pedidos", "abc")

    assert info.value.codigo == "E-PARAM-002"


# --- Catálogo de códigos ---------------------------------------------------


def test_catalog_has_the_per_type_staleness_codes_with_dataset_age_and_limit():
    texto = codigos.mensaje(
        codigos.E_CORRIDA_INVENTARIO_VIEJO,
        dataset="INVENTARIO", antiguedad=9, limite=7,
    )

    assert codigos.E_CORRIDA_INVENTARIO_VIEJO == "E-CORRIDA-003"
    assert "INVENTARIO" in texto and "9" in texto and "7" in texto


@pytest.mark.parametrize("codigo, esperado", [
    (codigos.E_CORRIDA_INVENTARIO_AUSENTE, "E-CORRIDA-002"),
    (codigos.E_CORRIDA_BACKORDER_AUSENTE, "E-CORRIDA-004"),
    (codigos.E_CORRIDA_BACKORDER_VIEJO, "E-CORRIDA-005"),
    (codigos.E_CORRIDA_FACTURAS_AUSENTE_O_VIEJA, "E-CORRIDA-006"),
    (codigos.E_CORRIDA_INGRESOS_AUSENTE_O_VIEJO, "E-CORRIDA-007"),
    (codigos.E_CARGA_ANULACION_BLOQUEADA, "E-CARGA-050"),
])
def test_catalog_codes_have_the_numbers_of_the_design(codigo, esperado):
    assert codigo == esperado
    assert codigo in codigos.CATALOGO


def test_every_catalog_key_follows_the_code_format():
    formato = re.compile(r"^(E|A)-(CORRIDA|PARAM|CARGA)-\d{3}$")

    assert len(codigos.CATALOGO) >= 20
    assert all(formato.match(c) for c in codigos.CATALOGO)


def test_param_messages_name_the_key_and_the_expected_domain():
    with pytest.raises(pc.ErrorParametro) as info:
        pc.validar_escritura("dias_entre_pedidos", 61)

    assert "dias_entre_pedidos" in info.value.mensaje
    assert "entre 1 y 60" in info.value.mensaje
