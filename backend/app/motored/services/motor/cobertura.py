"""
Motored Pedidos F3 "Motor" (ADR-2, decisiones #6a/#6b/#7) — cobertura por
clase, stock objetivo y puntos mínimo/máximo.

cobertura(clase) = dias_entre_pedidos/30 + I * k_fms / 30, con
I = dias_empaque + dias_transito + dias_seguridad y k según la letra FMS de la
clase (nunca la ABC). Con dias_entre_pedidos = 30 es idéntica a `1 + I*k/30`
del Excel. Las clases D (N <= 0) tienen cobertura 0.
"""
from fractions import Fraction
from typing import Optional

from app.motored.services.motor.aritmetica import a_fraccion
from app.motored.services.motor.tipos import AtributosSucursal, ParametrosMotor

DIAS_BASE_COBERTURA = Fraction(30)
_LETRAS_ABC = ("A", "B", "C", "D")


def intervalo_dias(atributos: AtributosSucursal) -> Fraction:
    """I = dias_empaque + dias_transito + dias_seguridad."""
    return (
        a_fraccion(atributos.dias_empaque)
        + a_fraccion(atributos.dias_transito)
        + a_fraccion(atributos.dias_seguridad)
    )


def _k_de_clase(clase: str, params: ParametrosMotor) -> Fraction:
    if len(clase) != 2 or clase[0] not in _LETRAS_ABC or clase[1] not in params.k_fms:
        raise ValueError(f"clase desconocida: {clase!r}")
    return a_fraccion(params.k_fms[clase[1]])


def cobertura_clase(clase: str, atributos: AtributosSucursal,
                    params: ParametrosMotor) -> Fraction:
    """Cobertura en meses de la clase ABC+FMS para esta sucursal."""
    k = _k_de_clase(clase, params)
    if clase[0] == "D":
        return Fraction(0)
    revision = a_fraccion(atributos.dias_entre_pedidos) / DIAS_BASE_COBERTURA
    return revision + intervalo_dias(atributos) * k / DIAS_BASE_COBERTURA


def stock_objetivo(n: Fraction, cobertura: Fraction) -> Fraction:
    """SS (Excel AA) = N x cobertura, exacto."""
    return n * cobertura


def punto_maximo(ss: Fraction) -> Fraction:
    """Punto máximo = stock objetivo (§6.9)."""
    return ss


def punto_minimo(n: Fraction, clase: str, atributos: AtributosSucursal,
                 params: ParametrosMotor) -> Fraction:
    """N x I x k / 30: no incluye el período de revisión (§6.9)."""
    k = _k_de_clase(clase, params)
    if clase[0] == "D":
        return Fraction(0)
    return n * intervalo_dias(atributos) * k / DIAS_BASE_COBERTURA


def cobertura_actual(y: Fraction, n: Fraction) -> Optional[Fraction]:
    """Y / N; nula sólo cuando N = 0 (N negativo da valor negativo, como Excel)."""
    return None if n == 0 else y / n
