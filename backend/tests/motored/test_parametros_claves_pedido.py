"""
Motored Pedidos F4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B5a,
ADR-6, spec TP-01..TP-07, DM-13, DM-14): las dos claves del tope de
presupuesto viven en el grupo nuevo PEDIDO, FUERA del motor.

- `modo_tope_presupuesto`: interruptor global (ADMIN), apagado por defecto.
- `presupuesto_maximo_pedido`: tope por tienda (decimal > 0 o nulo), ámbito
  sólo-sucursal: un valor global es E-PARAM-004.

Ninguna de las dos entra al snapshot de la corrida ni se puede usar como
override de un escenario, y no cambian ni un valor de lo que calcula el
motor (identidad con el interruptor apagado).
"""
import dataclasses
import datetime
import uuid
from fractions import Fraction

import pytest

from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.services import parametros, parametros_claves as pc
from app.motored.services.corridas import codigos
from app.motored.services.corridas import parametros_corrida as pcorr

MODO = "modo_tope_presupuesto"
TOPE = "presupuesto_maximo_pedido"
SUCURSAL = uuid.uuid4()
CORTE = datetime.date(2026, 10, 5)


def _codigo_de(clave, valor, sucursal_id=None):
    with pytest.raises(pc.ErrorParametro) as info:
        pc.validar_escritura(clave, valor, sucursal_id)
    return info.value.codigo


def _fila(clave, valor, sucursal_id=None):
    return ParametroMetodologia(
        id=uuid.uuid4(), clave=clave, valor=valor,
        vigente_desde=datetime.date(2026, 10, 1), sucursal_id=sucursal_id,
    )


def _construir(filas=()):
    vigentes = parametros.VigentesMotor.desde_filas(filas, CORTE)
    return pcorr.construir_parametros_corrida(vigentes, [SUCURSAL])


# --- Registro: grupo, ámbito y defaults ------------------------------------


def test_the_budget_keys_live_in_a_new_group_outside_the_engine():
    assert pc.GRUPO_PEDIDO == "PEDIDO"
    assert pc.GRUPO_PEDIDO != pc.GRUPO_MOTOR
    assert pc.REGISTRO[MODO].grupo == pc.GRUPO_PEDIDO
    assert pc.REGISTRO[TOPE].grupo == pc.GRUPO_PEDIDO


def test_the_switch_is_a_global_boolean_off_by_default():
    espec = pc.REGISTRO[MODO]

    assert espec.default is False
    assert espec.ambito == pc.AMBITO_GLOBAL


def test_the_cap_is_sucursal_only_and_has_no_default_number():
    espec = pc.REGISTRO[TOPE]

    assert espec.ambito == pc.AMBITO_SOLO_SUCURSAL
    assert espec.default is None


def test_the_per_sucursal_engine_key_keeps_its_own_scope():
    assert pc.REGISTRO["dias_entre_pedidos"].ambito == (
        pc.AMBITO_GLOBAL_Y_SUCURSAL)
    assert pc.AMBITO_SOLO_SUCURSAL not in {
        e.ambito for c, e in pc.REGISTRO.items() if c != TOPE}


# --- Escrituras: E-PARAM-004 y E-PARAM-002 ---------------------------------


def test_a_global_cap_is_e_param_004():
    assert _codigo_de(TOPE, "80000000") == "E-PARAM-004"
    assert codigos.E_PARAM_SOLO_SUCURSAL == "E-PARAM-004"


def test_the_e_param_004_message_names_the_key():
    with pytest.raises(pc.ErrorParametro) as info:
        pc.validar_escritura(TOPE, "80000000")

    assert TOPE in info.value.mensaje
    assert "tienda" in info.value.mensaje


@pytest.mark.parametrize("valor", [
    "80000000", 80000000, 80000000.5, "1", "0.01", None,
])
def test_a_cap_with_a_sucursal_accepts_a_positive_number_or_null(valor):
    pc.validar_escritura(TOPE, valor, SUCURSAL)


@pytest.mark.parametrize("valor", [
    0, -5, "0", "-5", "abc", "", True, False, [], {}, "NaN", "Infinity",
])
def test_a_cap_that_is_not_a_positive_number_is_e_param_002(valor):
    assert _codigo_de(TOPE, valor, SUCURSAL) == "E-PARAM-002"


@pytest.mark.parametrize("valor", [True, False])
def test_the_switch_accepts_a_boolean(valor):
    pc.validar_escritura(MODO, valor)


@pytest.mark.parametrize("valor", ["true", 1, 0, None, "si"])
def test_a_non_boolean_switch_is_e_param_002(valor):
    assert _codigo_de(MODO, valor) == "E-PARAM-002"


def test_the_switch_with_a_sucursal_is_e_param_003():
    assert _codigo_de(MODO, True, SUCURSAL) == "E-PARAM-003"


def test_the_global_check_comes_before_the_value_check():
    assert _codigo_de(TOPE, "abc") == "E-PARAM-004"


# --- Lectura tipada ---------------------------------------------------------


def test_a_stored_cap_parses_to_an_exact_fraction():
    assert pc.parsear(TOPE, "80000000.50") == Fraction(160000001, 2)
    assert pc.parsear(TOPE, None) is None


# --- Fuera del motor (TP-06, TP-07) ----------------------------------------


def test_the_engine_snapshot_keys_exclude_both_budget_keys():
    assert MODO not in pc.claves_motor()
    assert TOPE not in pc.claves_motor()


@pytest.mark.parametrize("clave", [MODO, TOPE])
def test_a_budget_key_is_not_a_valid_scenario_override(clave):
    with pytest.raises(pc.ErrorParametro) as info:
        pcorr.validar_overrides({clave: True})

    assert info.value.codigo == codigos.E_CORRIDA_OVERRIDE_INVALIDO
    assert clave in info.value.mensaje


def test_loaded_caps_and_the_switch_on_change_nothing_in_the_engine():
    base = _construir()
    con_tope = _construir([
        _fila(MODO, True),
        _fila(TOPE, "80000000", SUCURSAL),
    ])

    assert con_tope.motor == base.motor
    assert con_tope.snapshot == base.snapshot
    assert dataclasses.asdict(con_tope) == dataclasses.asdict(base)


def test_the_snapshot_never_mentions_the_budget_keys():
    resultado = _construir([
        _fila(MODO, True), _fila(TOPE, "80000000", SUCURSAL)])

    texto = repr(resultado.snapshot)

    assert MODO not in texto and TOPE not in texto


def test_the_reader_reports_no_cap_for_a_sucursal_without_a_row():
    """DM-14: sin fila el lector dice 'sin tope' (None), no un número."""
    vigentes = parametros.VigentesMotor.desde_filas([], CORTE)

    resolucion = vigentes.resolver(TOPE, SUCURSAL)

    assert resolucion.valor is None
    assert resolucion.fuente == parametros.FUENTE_DEFAULT


def test_the_switch_reads_false_by_default_and_true_when_written():
    """TP-01: sin filas el interruptor lee false (fuente default)."""
    vacio = parametros.VigentesMotor.desde_filas([], CORTE)
    escrito = parametros.VigentesMotor.desde_filas(
        [_fila(MODO, True)], CORTE)

    assert (vacio.resolver(MODO).valor, vacio.resolver(MODO).fuente) == (
        False, parametros.FUENTE_DEFAULT)
    assert (escrito.resolver(MODO).valor, escrito.resolver(MODO).fuente) == (
        True, parametros.FUENTE_GLOBAL)


# --- Catálogo de claves: tipo y opciones (B6 las expone) -------------------


TIPOS = {
    "bool", "entero", "decimal", "opcion", "k_fms", "lista",
    "lista_digitos", "mapa_opcion", "objeto_numerico", "tramos", "hora", "texto",
    "lista_opciones",
}


def test_every_key_declares_a_known_hashable_type():
    for clave, espec in pc.REGISTRO.items():
        assert espec.tipo in TIPOS, clave
        hash(espec.opciones)


def test_the_option_keys_carry_their_options_as_a_tuple():
    assert pc.REGISTRO["modo_mes_en_curso"].tipo == "opcion"
    assert pc.REGISTRO["modo_mes_en_curso"].opciones == (
        "EXCLUIDO", "PONDERADO")
    assert pc.REGISTRO["modo_redondeo_empaque"].opciones == (
        "CERCANO", "ARRIBA")


def test_only_the_option_keys_have_options():
    con_opciones = {c for c, e in pc.REGISTRO.items() if e.opciones}

    assert con_opciones == {
        "modo_mes_en_curso", "modo_redondeo_empaque", "grupo_por_cargo",
        "comision_base_pago", "cumplimiento_base", "aviso_roles_destino",
    }


@pytest.mark.parametrize("clave, tipo", [
    (MODO, "bool"), (TOPE, "decimal"), ("dias_entre_pedidos", "entero"),
    ("k_fms", "k_fms"), ("tipos_inventario_incluidos", "lista"),
    ("factor_demanda_perdida", "decimal"),
])
def test_the_type_of_each_kind_of_key(clave, tipo):
    assert pc.REGISTRO[clave].tipo == tipo


def test_a_spec_with_options_is_hashable_for_python_311():
    assert isinstance(hash(pc.REGISTRO["modo_mes_en_curso"].opciones), int)
    assert pc.REGISTRO["consolidar_sustituidas"].opciones == ()
