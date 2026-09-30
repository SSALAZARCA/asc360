"""
Motored Pedidos F3 "Motor" (ADR-2, decisión #6c) — pedido sugerido y valores
derivados.

pedido = max(0, ROUND((SS - Y + Z) / U) * U) con ROUND lejos de cero (CERCANO)
o techo (ARRIBA). Si eso da 0 y Z > 0, el pedido es Z sin redondear a U (el
clamp a 0 va ANTES de la regla de Z). U faltante o <= 0 da pedido 0 y una
advertencia, incluso con Z > 0 (IFERROR del Excel).
"""
from dataclasses import dataclass
from fractions import Fraction
from typing import Optional

from app.motored.services.motor.aritmetica import (
    a_fraccion,
    redondear_mitad_lejos_de_cero,
    techo,
)
from app.motored.services.motor.tipos import EntradaReferencia, ModoRedondeo

ADV_UNIDAD_EMPAQUE_INVALIDA = "UNIDAD_EMPAQUE_INVALIDA"


@dataclass(frozen=True)
class ResultadoPedido:
    pedido: Fraction
    advertencias: tuple[str, ...] = ()


def inventario_efectivo(entrada: EntradaReferencia) -> Fraction:
    """Y = V + W + X (inventario + tránsito + backorder)."""
    return (
        a_fraccion(entrada.inventario)
        + a_fraccion(entrada.transito)
        + a_fraccion(entrada.backorder)
    )


def _multiplos_de_unidad(neto: Fraction, unidad: int,
                         modo: ModoRedondeo) -> int:
    cuentas = neto / unidad
    if modo == "ARRIBA":
        return techo(cuentas)
    return redondear_mitad_lejos_de_cero(cuentas)


def calcular_pedido(ss: Fraction, y: Fraction, z: Fraction,
                    unidad: Optional[int],
                    modo: ModoRedondeo) -> ResultadoPedido:
    """Pedido sugerido exacto; devuelve además las advertencias del cálculo."""
    if unidad is None or unidad <= 0:
        return ResultadoPedido(Fraction(0), (ADV_UNIDAD_EMPAQUE_INVALIDA,))
    neto = ss - y + z
    multiplos = _multiplos_de_unidad(neto, unidad, modo)
    pedido = Fraction(max(0, multiplos * unidad))
    if pedido == 0 and z > 0:
        pedido = z
    return ResultadoPedido(pedido)


def valor_pedido(pedido: Fraction, precio: Optional[Fraction]) -> Fraction:
    """AC = pedido x precio normal; 0 cuando falta el precio."""
    return Fraction(0) if precio is None else pedido * precio


def cobertura_final(y: Fraction, pedido: Fraction,
                    n: Fraction) -> Optional[Fraction]:
    """AD = (Y + pedido) / N; nula sólo cuando N = 0."""
    return None if n == 0 else (y + pedido) / n
