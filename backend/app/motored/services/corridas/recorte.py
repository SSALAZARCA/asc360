"""
Motored Pedidos F4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B5a,
ADR-6, decisiones F4-7, F4-12, A2 y A3): propuesta de recorte de UNA tienda
al tope de presupuesto.

Módulo PURO: sin base de datos, sin I/O y sin SQLAlchemy (un test de AST lo
vigila). Recibe las líneas de la tienda y el tope y devuelve una propuesta
determinista; no escribe nada. Aplicarla (con su token) es de B5b.

Regla (F4-12):
- Sólo se recortan las líneas de clase C y, si no alcanza, las de clase B.
  Las clases A y D (A2: una D sólo tiene lo que COMPRAS le agregó a mano),
  las líneas sin clase, las de cantidad 0 y las sin precio no se tocan.
- Se corta UN empaque a la vez. En cada paso sale la línea que conserva la
  cobertura final MÁS ALTA después del corte, `(Y + pedido - paso) / N`; con
  N nula o 0 la cobertura cuenta como infinita y esa línea sale primero.
  Empate: código ascendente y, después, id de línea. Se recalcula el orden
  tras cada paso.
- A3: el primer paso de una línea que no es múltiplo del empaque la baja al
  múltiplo de abajo (25 con empaque 12: 24, luego 12, luego 0).
- Se corta hasta el primer valor <= tope. Si C y B se agotan y todavía hay
  exceso, queda como `exceso_residual` y A no se toca.

Todo en `Fraction`: ningún `float` toca un valor de dinero ni de cantidad.
"""
import heapq
from dataclasses import dataclass
from fractions import Fraction
from typing import Dict, Optional, Sequence, Tuple

# Orden en que se recortan las clases (la letra ABC de la línea).
CLASES_RECORTABLES = ("C", "B")

_CERO = Fraction(0)


@dataclass(frozen=True)
class LineaRecortable:
    """Una línea de la tienda, con lo que el recorte necesita de ella."""

    linea_id: int
    codigo: str
    clase_abc: Optional[str]
    pedido: Fraction
    unidad_empaque: int
    precio: Optional[Fraction]
    y: Fraction
    n: Optional[Fraction]


@dataclass(frozen=True)
class Recorte:
    """Lo que se le quita a UNA línea: de `pedido_actual` a
    `pedido_propuesto`, liberando `valor_recortado`."""

    linea_id: int
    codigo: str
    clase_abc: str
    pedido_actual: Fraction
    pedido_propuesto: Fraction
    valor_recortado: Fraction


@dataclass(frozen=True)
class PropuestaRecorte:
    tope: Fraction
    valor_actual: Fraction
    exceso: Fraction
    recortes: Tuple[Recorte, ...]
    valor_final: Fraction
    exceso_residual: Fraction
    lineas_sin_precio: int


class _Avance:
    """Estado mutable de UNA propuesta (nunca sale de este módulo)."""

    def __init__(self, lineas: Sequence[LineaRecortable], tope: Fraction):
        self.tope = tope
        self.actual: Dict[int, Fraction] = {
            x.linea_id: x.pedido for x in lineas}
        self.valor = _valor(lineas)


def _con_precio(linea: LineaRecortable) -> bool:
    return linea.precio is not None and linea.precio > 0


def _valor(lineas: Sequence[LineaRecortable]) -> Fraction:
    """Suma pedido x precio; una línea sin precio vale 0."""
    return sum(
        (x.pedido * x.precio for x in lineas if x.precio is not None),
        _CERO,
    )


def _paso(pedido: Fraction, unidad: int) -> Fraction:
    """Cuánto se le quita a la línea en el próximo paso (A3)."""
    if unidad <= 0:
        return pedido
    resto = pedido % unidad
    return resto if resto > 0 else Fraction(unidad)


def _clave(linea: LineaRecortable, actual: Fraction) -> tuple:
    """Clave de cola: la más baja sale primero. Primero las líneas de
    cobertura infinita (N nula o 0), luego la cobertura posterior más alta,
    luego código e id."""
    if not linea.n:
        return (0, _CERO, linea.codigo, linea.linea_id)
    cobertura = (linea.y + actual - _paso(actual, linea.unidad_empaque))
    return (1, -(cobertura / linea.n), linea.codigo, linea.linea_id)


def _candidatas(lineas: Sequence[LineaRecortable], clase: str) -> list:
    return [
        x for x in lineas
        if x.clase_abc == clase and x.pedido > 0 and _con_precio(x)
    ]


def _recortar_clase(
    candidatas: Sequence[LineaRecortable], avance: _Avance,
) -> None:
    """Corta una clase paso a paso hasta el tope o hasta agotarla."""
    por_id = {x.linea_id: x for x in candidatas}
    cola = [_clave(x, x.pedido) for x in candidatas]
    heapq.heapify(cola)
    while cola and avance.valor > avance.tope:
        linea = por_id[heapq.heappop(cola)[3]]
        actual = avance.actual[linea.linea_id]
        paso = _paso(actual, linea.unidad_empaque)
        avance.actual[linea.linea_id] = actual - paso
        avance.valor -= paso * linea.precio
        if actual - paso > 0:
            heapq.heappush(cola, _clave(linea, actual - paso))


def _recortes(
    lineas: Sequence[LineaRecortable], avance: _Avance,
) -> Tuple[Recorte, ...]:
    cortadas = [x for x in lineas if avance.actual[x.linea_id] != x.pedido]
    cortadas.sort(key=lambda x: (x.codigo, x.linea_id))
    return tuple(
        Recorte(
            x.linea_id, x.codigo, x.clase_abc, x.pedido,
            avance.actual[x.linea_id],
            (x.pedido - avance.actual[x.linea_id]) * x.precio,
        )
        for x in cortadas
    )


def _sin_precio(lineas: Sequence[LineaRecortable]) -> int:
    return sum(1 for x in lineas if x.pedido > 0 and not _con_precio(x))


def proponer_recorte(
    lineas: Sequence[LineaRecortable], tope: Fraction,
) -> PropuestaRecorte:
    """La propuesta de recorte de una tienda; no modifica sus argumentos."""
    avance = _Avance(lineas, tope)
    valor_actual = avance.valor
    for clase in CLASES_RECORTABLES:
        if avance.valor <= tope:
            break
        _recortar_clase(_candidatas(lineas, clase), avance)
    return PropuestaRecorte(
        tope=tope,
        valor_actual=valor_actual,
        exceso=max(_CERO, valor_actual - tope),
        recortes=_recortes(lineas, avance),
        valor_final=avance.valor,
        exceso_residual=max(_CERO, avance.valor - tope),
        lineas_sin_precio=_sin_precio(lineas),
    )
