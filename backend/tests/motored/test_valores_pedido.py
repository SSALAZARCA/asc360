"""
Fase 4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B2, ADR-3, spec ED-04,
ED-10..ED-14): reglas puras del valor y de la cantidad a pedir.

`valor` repite la cuantización del motor (mitad lejos de cero, 2 decimales,
sin precio = 0.00); `valor_sugerido` lo deriva del sugerido guardado;
`validar_cantidad` es la regla de E-CORRIDA-053; `fuera_de_empaque` es el
aviso de empaque (nunca bloquea) y `escapar_like` protege el filtro `q`.
"""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.motored.services.corridas import codigos, valores
from app.motored.services.corridas.codigos import ErrorCorrida

D = Decimal


# --- valor ------------------------------------------------------------------


def test_value_is_quantity_times_price_with_two_decimals():
    assert valores.valor(60, D("460.75")) == D("27645.00")
    assert valores.valor(D("50.00"), D("460.75")) == D("23037.50")


def test_value_rounds_half_away_from_zero_not_to_even():
    # 3 x 0.835 = 2.505: el redondeo bancario daría 2.50.
    assert valores.valor(3, D("0.835")) == D("2.51")
    assert valores.valor(1, D("0.005")) == D("0.01")


def test_value_without_a_price_is_zero_point_zero_zero():
    resultado = valores.valor(10, None)

    assert resultado == D("0.00") and str(resultado) == "0.00"


def test_value_of_zero_quantity_is_zero():
    assert str(valores.valor(0, D("460.75"))) == "0.00"


def test_the_suggested_value_comes_from_the_stored_suggestion():
    linea = SimpleNamespace(
        pedido_sugerido=D("50.00"), precio=D("460.75"))

    assert valores.valor_sugerido(linea) == D("23037.50")


@pytest.mark.parametrize("sugerido,precio", [
    (None, D("460.75")), (D("50.00"), None), (None, None)])
def test_the_suggested_value_is_zero_without_suggestion_or_price(
        sugerido, precio):
    linea = SimpleNamespace(pedido_sugerido=sugerido, precio=precio)

    assert str(valores.valor_sugerido(linea)) == "0.00"


# --- validar_cantidad (E-CORRIDA-053) ----------------------------------------


@pytest.mark.parametrize("bruto", [0, 1, 60, 9_999_999])
def test_a_whole_quantity_in_range_is_accepted(bruto):
    assert valores.validar_cantidad(bruto) == bruto


@pytest.mark.parametrize("bruto", [
    -1, 2.5, 60.0, "abc", "60", None, 10_000_000, True, False, [], {}])
def test_anything_else_is_a_coded_422_error(bruto):
    with pytest.raises(ErrorCorrida) as error:
        valores.validar_cantidad(bruto)

    assert error.value.codigo == codigos.E_CORRIDA_CANTIDAD_INVALIDA
    assert "9.999.999" in error.value.mensaje


# --- fuera_de_empaque (aviso, nunca bloquea) ---------------------------------


@pytest.mark.parametrize("cantidad,empaque,esperado", [
    (D("30.00"), 12, True),
    (D("13.00"), 12, True),
    (D("36.00"), 12, False),
    (D("0.00"), 12, False),
    (D("30.00"), 1, False),
    (D("30.00"), 0, False),
    (None, 12, False),
])
def test_the_pack_flag_follows_the_multiple_rule(
        cantidad, empaque, esperado):
    assert valores.fuera_de_empaque(cantidad, empaque) is esperado


# --- escapar_like -----------------------------------------------------------


@pytest.mark.parametrize("texto,esperado", [
    ("filtro", "filtro"),
    ("100%", "100\\%"),
    ("a_b", "a\\_b"),
    ("a\\b", "a\\\\b"),
    ("%_\\", "\\%\\_\\\\"),
])
def test_like_wildcards_are_escaped(texto, esperado):
    assert valores.escapar_like(texto) == esperado
