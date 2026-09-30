"""
Motored Pedidos F3 "Motor" (S8a) — oráculo independiente de la hoja `Pedido`.

Reimplementa las fórmulas del Excel (N, O, P, Q, R, S, AA..AD y el bloque
AA1:AE11) con `float`, igual que hace Excel, SIN usar el motor: así el libro
sintético que se genera a partir de aquí es una referencia externa para los
tests del extractor y del comparador. Sólo datos inventados.
"""
import math
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

PESOS = (1, 2, 3, 4, 5, 6)
CLASES = ("AF", "AM", "AS", "BF", "BM", "BS", "CF", "CM", "CS", "DS")
K_FMS = {"F": 3.0, "M": 1.5, "S": 1.0}
# El bloque AA1:AE11 del Excel real no tiene la fila CF (la fila 8 dice CM).
ETIQUETAS_EXCEL = ("AF", "AM", "AS", "BF", "BM", "BS", "CM", "CS", "DS")
ERROR_DIV_CERO = "#DIV/0!"


@dataclass(frozen=True)
class FilaSintetica:
    """Insumos de una fila; `clase_estatica` None = S coincide con Q + R."""

    codigo: str
    ventas: tuple
    precio: Optional[float] = None
    unidad: int = 1
    inventario: float = 0
    transito: float = 0
    backorder: float = 0
    ajuste: float = 0
    perdida: float = 0
    divisor: int = 21
    clase_estatica: Optional[str] = None


@dataclass(frozen=True)
class SucursalSintetica:
    nombre: str = "SUCURSAL SINTETICA"
    bodega: str = "BE999"
    sic: int = 1999
    dias_empaque: float = 3
    dias_transito: float = 2
    dias_seguridad: float = 2.5

    @property
    def intervalo(self) -> float:
        return self.dias_empaque + self.dias_transito + self.dias_seguridad


@dataclass(frozen=True)
class ResultadoHoja:
    """Valores cacheados por fila (letra de columna -> valor) y resumen."""

    filas: tuple
    coberturas: Mapping[str, float]
    resumen: tuple
    total: tuple


def redondear(valor: float) -> int:
    """ROUND(x, 0) de Excel: la mitad se aleja de cero."""
    magnitud = math.floor(abs(round(valor, 9)) + 0.5)
    return -magnitud if valor < 0 else magnitud


def coberturas(sucursal: SucursalSintetica) -> dict:
    """Fila 3 (E3:N3): 1 + I * k / 30 por clase; DS vale 0."""
    return {
        clase: 0.0 if clase == "DS" else
        1 + sucursal.intervalo * K_FMS[clase[1]] / 30
        for clase in CLASES
    }


def _letra_abc(n: float, acumulado: float) -> str:
    if n <= 0:
        return "D"
    if acumulado <= 0.8:
        return "A"
    return "B" if acumulado <= 0.95 else "C"


def _letra_fms(ventas: Sequence) -> str:
    meses = sum(1 for v in ventas if v > 0)
    return "F" if meses >= 2 else ("M" if meses >= 1 else "S")


def _pedido(ss: float, y: float, z: float, unidad: int) -> float:
    if unidad == 0:
        return 0
    bruto = max(0, redondear((ss - y + z) / unidad) * unidad)
    return z if bruto == 0 and z > 0 else bruto


def _demandas(filas: Sequence[FilaSintetica]) -> list:
    return [
        sum(v * peso for v, peso in zip(f.ventas, PESOS)) / f.divisor
        for f in filas
    ]


def _fila_calculada(fila: FilaSintetica, n: float, total: float,
                    corrido: float, cobs: Mapping[str, float]) -> dict:
    acumulado = corrido / total
    q, r = _letra_abc(n, acumulado), _letra_fms(fila.ventas)
    s = fila.clase_estatica or q + r
    y = fila.inventario + fila.transito + fila.backorder
    ss = n * cobs.get(s, 0.0)
    ab = _pedido(ss, y, fila.ajuste, fila.unidad)
    precio = "" if fila.precio is None else fila.precio
    return {
        "K": fila.perdida, "N": n, "O": n / total, "P": acumulado,
        "Q": q, "R": r, "S": s, "T": precio, "U": fila.unidad,
        "V": fila.inventario, "W": fila.transito, "X": fila.backorder,
        "Y": y, "AA": ss, "AB": ab,
        "AC": ab * fila.precio if fila.precio is not None else 0,
        "AD": (y + ab) / n if n != 0 else ERROR_DIV_CERO,
    }


def _resumen(filas: Sequence[dict], etiquetas: Sequence[str]) -> tuple:
    bloques = []
    for etiqueta in etiquetas:
        propias = [f for f in filas if f["S"] == etiqueta]
        bloques.append([
            etiqueta, sum(f["AB"] for f in propias),
            sum(1 for f in propias if f["AB"] > 0),
            sum(f["AC"] for f in propias),
        ])
    unidades = sum(b[1] for b in bloques)
    filas_resumen = tuple(
        (b[0], b[1], b[2], b[3], b[1] / unidades if unidades else 0.0)
        for b in bloques
    )
    total = ("Total general", unidades, sum(b[2] for b in bloques),
             sum(b[3] for b in bloques), 1.0 if unidades else 0.0)
    return filas_resumen, total


def calcular_hoja(filas: Sequence[FilaSintetica],
                  sucursal: SucursalSintetica, *,
                  etiquetas: Sequence[str] = ETIQUETAS_EXCEL,
                  sobrescribe: Optional[Mapping[str, Mapping]] = None
                  ) -> ResultadoHoja:
    """Valores cacheados de la hoja; las filas van en orden físico.

    `sobrescribe` (`{código: {columna: valor}}`) pisa valores ya calculados
    antes de armar el resumen: permite simular artefactos del Excel.
    """
    cobs = coberturas(sucursal)
    demandas = _demandas(filas)
    total, corrido, calculadas = sum(demandas), 0.0, []
    for fila, n in zip(filas, demandas):
        corrido += n
        valores = _fila_calculada(fila, n, total, corrido, cobs)
        valores.update((sobrescribe or {}).get(fila.codigo, {}))
        calculadas.append(valores)
    resumen, total_resumen = _resumen(calculadas, etiquetas)
    return ResultadoHoja(tuple(calculadas), cobs, resumen, total_resumen)
