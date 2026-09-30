"""
Motored Pedidos F3 "Motor" (ADR-2, spec 6.9) — estado de quiebre.

Se calcula y se guarda; ninguna pantalla lo usa en F3. Los puntos mínimo y
máximo viven en `cobertura.py`. La primera regla que aplica gana:

1. N <= 0 y Y <= 0                       -> SIN_MOVIMIENTO
2. N <= 0 y Y > 0                        -> INVENTARIO_MUERTO si no hubo venta
   en los últimos `meses_inventario_muerto` meses; si hubo, SOBRESTOCK
3. Y <= 0                                -> QUIEBRE_TOTAL
4. V <= 0 y W + X > 0                    -> QUIEBRE_PISO
5. Y < punto mínimo                      -> BAJO_MINIMO
6. Y > punto máximo x (1 + tolerancia)   -> SOBRESTOCK
7. en otro caso                          -> NORMAL
"""
from fractions import Fraction
from typing import Sequence

from app.motored.services.motor.aritmetica import a_fraccion
from app.motored.services.motor.tipos import ParametrosMotor

SIN_MOVIMIENTO = "SIN_MOVIMIENTO"
INVENTARIO_MUERTO = "INVENTARIO_MUERTO"
SOBRESTOCK = "SOBRESTOCK"
QUIEBRE_TOTAL = "QUIEBRE_TOTAL"
QUIEBRE_PISO = "QUIEBRE_PISO"
BAJO_MINIMO = "BAJO_MINIMO"
NORMAL = "NORMAL"


def _hubo_venta_reciente(ventas: Sequence[Fraction], meses: int) -> bool:
    """¿Hubo venta > 0 en los últimos `meses` cubos cerrados (M1..M6)?"""
    if meses <= 0:
        return False
    return any(v > 0 for v in ventas[max(0, len(ventas) - meses):])


def _sin_demanda(inventario_total: Fraction, ventas: Sequence[Fraction],
                 params: ParametrosMotor) -> str:
    if inventario_total <= 0:
        return SIN_MOVIMIENTO
    if _hubo_venta_reciente(ventas, params.meses_inventario_muerto):
        return SOBRESTOCK
    return INVENTARIO_MUERTO


def estado_quiebre(*, n: Fraction, inventario: Fraction, transito: Fraction,
                   backorder: Fraction, punto_minimo: Fraction,
                   punto_maximo: Fraction, ventas: Sequence[Fraction],
                   params: ParametrosMotor) -> str:
    """Estado de quiebre de una línea (V, W, X y Y ya son los efectivos)."""
    y = inventario + transito + backorder
    if n <= 0:
        return _sin_demanda(y, ventas, params)
    if y <= 0:
        return QUIEBRE_TOTAL
    if inventario <= 0 and transito + backorder > 0:
        return QUIEBRE_PISO
    if y < punto_minimo:
        return BAJO_MINIMO
    tolerancia = a_fraccion(params.tolerancia_sobrestock)
    if y > punto_maximo * (1 + tolerancia):
        return SOBRESTOCK
    return NORMAL
