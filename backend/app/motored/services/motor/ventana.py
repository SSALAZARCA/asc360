"""
Motored Pedidos F3 "Motor" (ADR-2, spec §6.4.5) — ventana de seis meses
completos y divisor dinámico.

Para un corte en el mes m, la ventana son los meses m-6..m-1 (M6..M1) con
pesos 1..6 (suma 21). Un mes cuenta sólo si la sucursal ya estaba abierta el
primer día de ese mes; los meses cerrados antes de la apertura salen del
numerador y del divisor. Sin switch: es comportamiento fijo.
"""
from dataclasses import dataclass
from datetime import date
from typing import Optional

MESES_VENTANA = 6
PESOS_BASE = (1, 2, 3, 4, 5, 6)
DIVISOR_BASE = sum(PESOS_BASE)


@dataclass(frozen=True)
class Ventana:
    """Meses (anio, mes) M6..M1, pesos efectivos (0 = mes no operado)."""

    meses: tuple[tuple[int, int], ...]
    pesos: tuple[int, ...]
    divisor: int

    @property
    def sin_historia(self) -> bool:
        """Divisor 0: la sucursal no tiene ningún mes completo operado."""
        return self.divisor == 0


def _desplazar_mes(anio: int, mes: int, delta: int) -> tuple[int, int]:
    indice = anio * 12 + (mes - 1) + delta
    return indice // 12, indice % 12 + 1


def meses_de_la_ventana(fecha_corte: date) -> tuple[tuple[int, int], ...]:
    """Los seis meses completos previos al mes del corte, de M6 a M1."""
    return tuple(
        _desplazar_mes(fecha_corte.year, fecha_corte.month, -(MESES_VENTANA - i))
        for i in range(MESES_VENTANA)
    )


def _mes_operado(mes: tuple[int, int], fecha_apertura: Optional[date]) -> bool:
    if fecha_apertura is None:
        return True
    return fecha_apertura <= date(mes[0], mes[1], 1)


def construir_ventana(
    fecha_corte: date, fecha_apertura: Optional[date]
) -> Ventana:
    """Ventana y divisor efectivo para una sucursal y un corte."""
    meses = meses_de_la_ventana(fecha_corte)
    pesos = tuple(
        peso if _mes_operado(mes, fecha_apertura) else 0
        for mes, peso in zip(meses, PESOS_BASE)
    )
    return Ventana(meses=meses, pesos=pesos, divisor=sum(pesos))
