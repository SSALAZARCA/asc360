"""
Motored Pedidos F3 "Motor" (ADR-2) — resumen por clase de una sucursal.

Replica el bloque AA1:AE11 del Excel: una fila por cada una de las diez
clases (AF..CS y DS) con unidades pedidas, referencias con pedido > 0, valor
y peso de las unidades, más una fila de totales. Sólo entran las líneas del
pedido; las transferidas o sin reemplazo no suman.

`porcentaje_peso` es la fracción de las unidades de la sucursal (0..1; la
suma de las filas da 1) y vale 0 cuando el total de unidades es 0. Una clase
fuera del bloque (por ejemplo DM: N <= 0 con ventas en un mes) se agrega al
final para que los totales nunca pierdan unidades.
"""
from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable

CLASES_RESUMEN = ("AF", "AM", "AS", "BF", "BM", "BS", "CF", "CM", "CS", "DS")
CLASE_TOTAL = "TOTAL"


@dataclass(frozen=True)
class FilaResumen:
    clase: str
    unidades: Fraction
    referencias: int
    valor: Fraction
    porcentaje_peso: Fraction


@dataclass(frozen=True)
class ResumenSucursal:
    filas: tuple[FilaResumen, ...]
    total: FilaResumen


def _sumar(lineas: list[tuple[str, Fraction, Fraction]]) -> tuple:
    unidades = sum((p for _, p, _ in lineas), Fraction(0))
    referencias = sum(1 for _, p, _ in lineas if p > 0)
    valor = sum((v for _, _, v in lineas), Fraction(0))
    return unidades, referencias, valor


def _peso(unidades: Fraction, total: Fraction) -> Fraction:
    return unidades / total if total else Fraction(0)


def resumir(lineas: Iterable[tuple[str, Fraction, Fraction]]
            ) -> ResumenSucursal:
    """Resumen a partir de tuplas `(clase, pedido, valor_pedido)`."""
    lineas = list(lineas)
    extras = sorted({c for c, _, _ in lineas} - set(CLASES_RESUMEN))
    total_unidades, total_refs, total_valor = _sumar(lineas)
    filas = []
    for clase in CLASES_RESUMEN + tuple(extras):
        unidades, referencias, valor = _sumar(
            [linea for linea in lineas if linea[0] == clase]
        )
        filas.append(FilaResumen(
            clase, unidades, referencias, valor,
            _peso(unidades, total_unidades),
        ))
    total = FilaResumen(
        CLASE_TOTAL, total_unidades, total_refs, total_valor,
        _peso(total_unidades, total_unidades),
    )
    return ResumenSucursal(tuple(filas), total)
