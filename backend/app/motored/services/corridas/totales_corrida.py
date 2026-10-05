"""
Motored Pedidos: the totals of a WHOLE corrida (all visible stores), shown
above the tabs of the detail and on each row of the corridas list.

The one rule, used by both reads:

- `unidades`: the sum of `pedido_final` and `valor_total` the sum of
  `valor_pedido` over the non-excluded lines: exactly what the Tiendas tab
  adds per store (`consultas._a_pedir`), so the totals equal the sum of
  the per-store "A pedir" figures. An unpriced line keeps `valor_pedido`
  at 0.00 (`valores.valor`): it counts its units but adds no value.
- `referencias`: the DISTINCT referencia codes with a quantity above zero
  across the stores.

A corrida whose calculation has not finished (anything but `CALCULADAS`)
has no totals: `None`, and the screen shows a dash. The list reads the
aggregate inside its page query (a LATERAL subquery per row, never one
query per corrida); the detail runs it as one extra read.
"""
from decimal import Decimal
from typing import Any, Dict, FrozenSet, Optional
from uuid import UUID

from sqlalchemy import distinct, func, select

from app.motored.models.corrida_linea import CorridaLinea
from app.motored.services.corridas import estados

Alcance = Optional[FrozenSet[UUID]]


def _agregados() -> list:
    """The three aggregates, labeled as the projection reads them."""
    cl = CorridaLinea
    return [
        func.sum(cl.valor_pedido).label("valor_total"),
        func.count(distinct(cl.codigo_referencia))
        .filter(cl.pedido_final > 0).label("referencias_total"),
        func.sum(cl.pedido_final).label("unidades_total"),
    ]


def _condiciones(corrida_id, alcance: Alcance) -> list:
    """Lines of the corrida (a value or a correlated column), never the
    excluded ones, only from the visible sucursales."""
    cl = CorridaLinea
    condiciones = [cl.corrida_id == corrida_id, cl.motivo_exclusion.is_(None)]
    if alcance is not None:
        condiciones.append(cl.sucursal_id.in_(sorted(alcance)))
    return condiciones


def subconsulta_lista(corrida_id_columna, alcance: Alcance):
    """The aggregate correlated to each row of the list page (LATERAL)."""
    return (
        select(*_agregados())
        .where(*_condiciones(corrida_id_columna, alcance))
        .lateral("totales_corrida"))


def consulta_de_corrida(corrida_id: UUID, alcance: Alcance):
    """The aggregate of one corrida (the detail)."""
    return select(*_agregados()).where(*_condiciones(corrida_id, alcance))


def proyectar(
    estado: str, valor_total: Any, referencias: Any, unidades: Any,
) -> Optional[Dict[str, Any]]:
    """`{valor_total, referencias, unidades}`, or `None` while the corrida
    is not calculated. A sum over no lines (NULL) is zero."""
    if estado not in estados.CALCULADAS:
        return None
    return {
        "valor_total": Decimal(0) if valor_total is None else valor_total,
        "referencias": referencias or 0,
        "unidades": Decimal(0) if unidades is None else unidades,
    }


def de_fila(fila) -> Optional[Dict[str, Any]]:
    """The totals of a list row (columns of `subconsulta_lista`)."""
    return proyectar(
        fila.estado, getattr(fila, "valor_total", None),
        getattr(fila, "referencias_total", None),
        getattr(fila, "unidades_total", None))


async def de_corrida(db, corrida, alcance: Alcance) -> Optional[dict]:
    """The totals of one corrida; no read while it is not calculated."""
    if corrida.estado not in estados.CALCULADAS:
        return None
    resultado = await db.execute(consulta_de_corrida(corrida.id, alcance))
    fila = resultado.first()
    if fila is None:
        return proyectar(corrida.estado, None, None, None)
    return proyectar(
        corrida.estado, fila.valor_total, fila.referencias_total,
        fila.unidades_total)
