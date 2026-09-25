"""Unit tests for `lore.handlers._common` — shared helpers/constants used by
every handler module.

Phase 10 fix-up finding #6: the quantity-validation logic (`_CANTIDAD_MINIMA`,
`_CANTIDAD_MAXIMA`, and the `isdigit()`+bounds check) used to be duplicated
byte-for-byte between `captura.py::recibir_cantidad` and
`correccion.py::recibir_cantidad`. Hoisted here so a future bounds change
only needs to happen in one place.
"""
from lore.handlers._common import _CANTIDAD_MAXIMA, _CANTIDAD_MINIMA, _validar_cantidad


def test_validar_cantidad_accepts_minimum_boundary():
    assert _validar_cantidad("1") == 1
    assert _CANTIDAD_MINIMA == 1


def test_validar_cantidad_accepts_maximum_boundary():
    assert _validar_cantidad("9999") == 9999
    assert _CANTIDAD_MAXIMA == 9999


def test_validar_cantidad_rejects_zero():
    assert _validar_cantidad("0") is None


def test_validar_cantidad_rejects_above_maximum():
    assert _validar_cantidad("10000") is None


def test_validar_cantidad_rejects_non_digit_text():
    assert _validar_cantidad("abc") is None
    assert _validar_cantidad("") is None
    assert _validar_cantidad("-5") is None
