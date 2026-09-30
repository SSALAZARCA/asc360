"""
Motored Pedidos F3 "Motor" (S8a) — conjuntos de filas sintéticas para los
tests del extractor y del comparador. Sólo datos inventados.

El conjunto base está armado para que:

- nivel A1 (divisor 18 de C-300 y orden físico) coincida en todo;
- nivel A2 (divisor 21) cambie el N de C-300 (T1) y mueva la clase de B-200
  de A a B (T2) sin cambiar su pedido.
"""
from tests.motored.fixtures.regresion.oraculo_excel import FilaSintetica

CODIGO_18 = "C-300"
CODIGO_MOVIDO = "B-200"


def filas_base() -> list:
    """Seis filas ordenadas por N descendente (orden físico del Excel)."""
    return [
        FilaSintetica(
            "A-100", (50,) * 6, precio=100.0, inventario=10, transito=5,
        ),
        FilaSintetica(
            CODIGO_MOVIDO, (22,) * 6, precio=55.5, unidad=12,
            inventario=40, backorder=3,
        ),
        FilaSintetica(
            CODIGO_18, (10,) * 6, precio=20.0, inventario=2, divisor=18,
        ),
        FilaSintetica("D-400", (5,) * 6, precio=None, inventario=0),
        FilaSintetica(
            "E-500", (0, 0, 0, 4, 0, 2), precio=8.0, inventario=100,
            ajuste=15,
        ),
        FilaSintetica(
            "F-600", (0, 0, 0, 0, 0, 3), precio=10.0, inventario=1,
            transito=1,
        ),
    ]


def filas_con_empate() -> list:
    """G-1 y G-2 empatan en N; el Excel las deja en orden físico G-2, G-1."""
    return [
        FilaSintetica("H-0", (40,) * 6, precio=10.0),
        FilaSintetica("G-2", (20,) * 6, precio=10.0),
        FilaSintetica("G-1", (20,) * 6, precio=10.0),
        FilaSintetica("I-9", (2,) * 6, precio=10.0),
    ]
