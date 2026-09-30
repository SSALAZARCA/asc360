"""
Motored Pedidos F3 "Motor" (sdd/motored-pedidos-motor, S1-1) — aritmética
exacta del motor puro (ADR-1: `Fraction`, cuantizar sólo al persistir).
"""
from decimal import Decimal
from fractions import Fraction

import pytest

from app.motored.services.motor.aritmetica import (
    a_fraccion,
    cuantizar,
    redondear_mitad_lejos_de_cero,
    techo,
)


class TestAFraccion:
    def test_acepta_decimal_int_y_str(self):
        assert a_fraccion(Decimal("2.50")) == Fraction(5, 2)
        assert a_fraccion(7) == Fraction(7)
        assert a_fraccion("0.125") == Fraction(1, 8)

    def test_acepta_fraccion_sin_cambios(self):
        assert a_fraccion(Fraction(1, 3)) == Fraction(1, 3)

    @pytest.mark.parametrize("valor", [0.1, 1.0, float("nan")])
    def test_rechaza_float(self, valor):
        with pytest.raises(TypeError):
            a_fraccion(valor)

    def test_rechaza_bool(self):
        with pytest.raises(TypeError):
            a_fraccion(True)

    def test_rechaza_decimal_no_finito(self):
        with pytest.raises(ValueError):
            a_fraccion(Decimal("NaN"))


class TestRedondeoMitadLejosDeCero:
    @pytest.mark.parametrize(
        "valor, esperado",
        [
            (Fraction(99, 2), 50),
            (Fraction(-1, 2), -1),
            (Fraction(-99, 2), -50),
            (Fraction(1, 2), 1),
            (Fraction(49, 100), 0),
            (Fraction(-49, 100), 0),
            (Fraction(3, 2), 2),
            (Fraction(5, 2), 3),
            (Fraction(0), 0),
            (Fraction(7), 7),
        ],
    )
    def test_tabla(self, valor, esperado):
        assert redondear_mitad_lejos_de_cero(valor) == esperado

    def test_no_es_redondeo_bancario(self):
        # Round() de Python daría 2 para 5/2; Excel ROUND da 3.
        assert redondear_mitad_lejos_de_cero(Fraction(5, 2)) == 3


class TestTecho:
    @pytest.mark.parametrize(
        "valor, esperado",
        [
            (Fraction(5, 12), 1),
            (Fraction(0), 0),
            (Fraction(-1, 2), 0),
            (Fraction(12, 12), 1),
            (Fraction(13, 12), 2),
        ],
    )
    def test_tabla(self, valor, esperado):
        assert techo(valor) == esperado


class TestCuantizar:
    @pytest.mark.parametrize(
        "valor, lugares, esperado",
        [
            (Fraction(1, 2), 0, "1"),
            (Fraction(-1, 2), 0, "-1"),
            (Fraction(5, 1000), 2, "0.01"),
            (Fraction(-5, 1000), 2, "-0.01"),
            (Fraction(49, 1000), 2, "0.05"),
            (Fraction(598, 7), 6, "85.428571"),
            (Fraction(1029, 598), 6, "1.720736"),
            (Fraction(0), 2, "0.00"),
        ],
    )
    def test_mitad_hacia_arriba_lejos_de_cero(self, valor, lugares, esperado):
        resultado = cuantizar(valor, lugares)
        assert resultado == Decimal(esperado)
        assert str(resultado) == esperado

    def test_devuelve_decimal(self):
        assert isinstance(cuantizar(Fraction(1, 3), 4), Decimal)
