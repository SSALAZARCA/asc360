"""
Motored Pedidos F3 "Motor" (ADR-1) — aritmética exacta.

Todo el motor opera con `Fraction`: cada operación es +, -, x, / o una
comparación sobre racionales, así que ningún .5 de frontera se pierde por
error binario ni por redondeos intermedios (la fila patrón §10.1 da 50 y no 49).

Los valores entran por `a_fraccion` (nunca `float`) y salen por `cuantizar`
sólo al persistir; un valor cuantizado jamás vuelve a un cálculo.
"""
import math
from decimal import Decimal
from fractions import Fraction
from typing import Union

Numero = Union[Fraction, Decimal, int, str]


def a_fraccion(valor: Numero) -> Fraction:
    """Convierte `Decimal`/`int`/`str`/`Fraction` a `Fraction` exacta.

    `float` y `bool` levantan `TypeError`: un float ya trae error binario y
    aceptarlo rompería la garantía de exactitud.
    """
    if isinstance(valor, (bool, float)):
        raise TypeError(f"a_fraccion no acepta {type(valor).__name__}")
    if isinstance(valor, Decimal) and not valor.is_finite():
        raise ValueError(f"valor no finito: {valor}")
    return Fraction(valor)


def redondear_mitad_lejos_de_cero(valor: Fraction) -> int:
    """ROUND de Excel: la mitad se aleja de cero (49.5 -> 50, -0.5 -> -1)."""
    magnitud = math.floor(abs(valor) + Fraction(1, 2))
    return -magnitud if valor < 0 else magnitud


def techo(valor: Fraction) -> int:
    """Entero más pequeño mayor o igual que `valor` (modo ARRIBA)."""
    return math.ceil(valor)


def cuantizar(valor: Fraction, lugares: int) -> Decimal:
    """Cuantiza a `lugares` decimales con ROUND_HALF_UP (lejos de cero).

    Es la única salida de `Fraction` a `Decimal`: se usa al persistir.
    """
    escalado = redondear_mitad_lejos_de_cero(valor * (10 ** lugares))
    return Decimal(escalado).scaleb(-lugares)
