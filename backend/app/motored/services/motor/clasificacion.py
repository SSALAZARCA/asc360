"""
Motored Pedidos F3 "Motor" (ADR-2, decisión #3) — clasificación ABC y FMS.

Reglas del Excel (ganan sobre el texto del spec 6.5.1):

- Peso = N / suma de N sobre TODAS las filas del universo, incluidas las de
  N <= 0. El acumulado incluye la fila actual y se recorre en orden de N
  descendente, con desempate determinista (`orden_explicito` si existe, si no
  el código ascendente).
- Empates (decisión #17): las referencias con N exactamente igual forman un
  grupo y todas reciben la clase de la PRIMERA posición del grupo, es decir
  la del acumulado que alcanza su primer miembro. El orden (`orden`), el peso
  y el acumulado de cada fila siguen siendo por fila: sólo la clase se
  unifica, así que un miembro puede mostrar un acumulado por encima del corte
  de la clase que lleva. Así el ABC deja de depender del código o del orden
  físico del Excel. El Excel clasifica fila por fila; `empates_como_excel`
  (sólo nivel A1) reproduce eso.
- Clase ABC: D si N <= 0; A si el acumulado <= corte A (80 %); B si <= corte B
  (95 %); C si es mayor. Las comparaciones son exactas (`Fraction`).
- Clase de la línea (decisión #19): toda referencia con N <= 0 es "DS", sea
  cual sea su letra FMS (el Excel la rotula DM/DF; `clase_d_como_excel`,
  sólo nivel A1, lo reproduce). La letra FMS sigue en `clase_fms`. Lo compone
  el ensamblador del motor (`motor._etiqueta_clase`).
- FMS: meses con venta neta > 0 entre los seis cerrados (F >= umbral F, M >=
  umbral M, si no S). La demanda perdida y el mes en curso no cuentan, y los
  meses anteriores a la apertura de la sucursal tampoco.
"""
from dataclasses import dataclass
from fractions import Fraction
from typing import Mapping, Optional, Sequence

from app.motored.services.motor.aritmetica import a_fraccion
from app.motored.services.motor.tipos import EntradaReferencia, ParametrosMotor
from app.motored.services.motor.ventana import Ventana

CLASE_D_SIN_DEMANDA = "DS"


@dataclass(frozen=True)
class ItemAbc:
    """Posición de una fila en el ABC de la sucursal (orden desde 1)."""

    orden: int
    clase: str
    peso: Optional[Fraction]
    acumulado: Optional[Fraction]


@dataclass(frozen=True)
class ResultadoAbc:
    """ABC de una sucursal; `suma_no_positiva` dispara A-CORRIDA-110."""

    items: Mapping[str, ItemAbc]
    suma_no_positiva: bool


def ventas_efectivas(entrada: EntradaReferencia,
                     ventana: Ventana) -> tuple[Fraction, ...]:
    """Ventas M6..M1 sin demanda perdida; los meses no operados valen 0."""
    return tuple(
        a_fraccion(v) if peso else Fraction(0)
        for v, peso in zip(entrada.ventas, ventana.pesos)
    )


def meses_con_venta(ventas: Sequence[Fraction]) -> int:
    """Meses con venta neta estrictamente positiva."""
    return sum(1 for v in ventas if v > 0)


def clase_fms(meses: int, params: ParametrosMotor) -> str:
    """Letra FMS según los umbrales de los parámetros (2 y 1 por defecto)."""
    if meses >= params.umbral_f:
        return "F"
    if meses >= params.umbral_m:
        return "M"
    return "S"


def _clave_de_orden(codigo: str, n: Fraction,
                    desempate: Optional[Mapping[str, int]]):
    rango = 0 if desempate is None else desempate.get(codigo, len(desempate))
    return (-n, rango, codigo)


def _letra_abc(n: Fraction, acumulado: Fraction,
               params: ParametrosMotor) -> str:
    if n <= 0:
        return "D"
    if acumulado <= a_fraccion(params.corte_abc_a):
        return "A"
    if acumulado <= a_fraccion(params.corte_abc_b):
        return "B"
    return "C"


def _abc_sin_total_positivo(orden: Sequence[str],
                            demandas: Mapping[str, Fraction]) -> ResultadoAbc:
    """Suma de N <= 0: las de N > 0 quedan en C y sin pesos (A-CORRIDA-110)."""
    items = {
        codigo: ItemAbc(
            posicion, "C" if demandas[codigo] > 0 else "D", None, None
        )
        for posicion, codigo in enumerate(orden, start=1)
    }
    return ResultadoAbc(items, suma_no_positiva=True)


def _clases_por_grupo(orden: Sequence[str],
                      demandas: Mapping[str, Fraction], total: Fraction,
                      params: ParametrosMotor) -> dict[str, str]:
    """Clase de cada código: la de la primera posición de su grupo de N."""
    clases: dict[str, str] = {}
    corrido = Fraction(0)
    n_grupo = None
    clase_grupo = "D"
    for codigo in orden:
        n = demandas[codigo]
        corrido += n
        if n != n_grupo:
            n_grupo = n
            clase_grupo = _letra_abc(n, corrido / total, params)
        clases[codigo] = clase_grupo
    return clases


def clasificar_abc(demandas: Mapping[str, Fraction], params: ParametrosMotor,
                   *, desempate: Optional[Mapping[str, int]] = None,
                   empates_como_excel: bool = False) -> ResultadoAbc:
    """ABC de una sucursal a partir de `{código: N}` de todo el universo."""
    orden = sorted(
        demandas, key=lambda c: _clave_de_orden(c, demandas[c], desempate)
    )
    total = sum(demandas.values(), Fraction(0))
    if orden and total <= 0:
        return _abc_sin_total_positivo(orden, demandas)
    grupos = _clases_por_grupo(orden, demandas, total, params)
    items = {}
    corrido = Fraction(0)
    for posicion, codigo in enumerate(orden, start=1):
        n = demandas[codigo]
        corrido += n
        acumulado = corrido / total
        clase = (
            _letra_abc(n, acumulado, params) if empates_como_excel
            else grupos[codigo]
        )
        items[codigo] = ItemAbc(posicion, clase, n / total, acumulado)
    return ResultadoAbc(items, suma_no_positiva=False)
