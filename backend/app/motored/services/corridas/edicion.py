"""
Motored Pedidos F4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B2,
ADR-3, decisiones F4-2..F4-4): edición de la cantidad a pedir de una línea.

`editar_linea` cambia `pedido_final` (y `valor_pedido`, que lo sigue) de UNA
línea mientras el pedido de su tienda esté en BORRADOR, y deja una fila en
`corrida_linea_historial` en la MISMA transacción: si el historial falla, el
cambio se deshace. Las salidas del motor (`pedido_sugerido` y el resto) no se
tocan nunca.

Orden de los chequeos (spec, convención 14): corrida (404), línea (404),
escenario (042), cálculo (040), invalidada (041), tienda sin pedido (065),
pedido no BORRADOR (052), cantidad (053), línea excluida (054) y cantidad
esperada (066). Orden de los bloqueos (`bloqueos.py`): corrida `FOR SHARE` ->
tienda `FOR SHARE` -> línea `FOR UPDATE`; las ediciones de tiendas distintas
no se esperan y un cierre de la tienda (que la toma `FOR UPDATE`) espera a
las ediciones en vuelo y las ve cerradas después.

Ningún commit acá: la transacción es del llamador.
"""
from decimal import Decimal
from typing import Any, Dict, NamedTuple, Optional
from uuid import UUID

from sqlalchemy import func, insert, select

from app.motored.models.corrida_linea import CorridaLinea
from app.motored.models.corrida_linea_historial import CorridaLineaHistorial
from app.motored.services.corridas import (
    bloqueos,
    codigos,
    consultas,
    estados,
    valores,
)
from app.motored.services.corridas.codigos import ErrorCorrida
from app.motored.services.corridas.proyecciones import UltimaEdicion

ACCION = "editar"
MOTIVO_MANUAL = "MANUAL"


class ResultadoEdicion(NamedTuple):
    """La línea tal como quedó, su última edición y los totales de la
    tienda (a pedir y sugerido)."""

    linea: Any
    ultima_edicion: Optional[UltimaEdicion]
    totales_tienda: Dict[str, Decimal]


def _exigir_borrador(tienda: Any) -> None:
    if tienda.estado_pedido is None:
        raise ErrorCorrida(
            codigos.E_CORRIDA_SIN_PEDIDO,
            codigos.mensaje(codigos.E_CORRIDA_SIN_PEDIDO))
    if tienda.estado_pedido != estados.PEDIDO_BORRADOR:
        raise ErrorCorrida(
            codigos.E_CORRIDA_PEDIDO_NO_BORRADOR,
            codigos.mensaje(
                codigos.E_CORRIDA_PEDIDO_NO_BORRADOR,
                estado=tienda.estado_pedido))


def _exigir_editable(linea: Any, esperado: Optional[Decimal]) -> None:
    if linea.motivo_exclusion is not None:
        raise ErrorCorrida(
            codigos.E_CORRIDA_LINEA_EXCLUIDA,
            codigos.mensaje(
                codigos.E_CORRIDA_LINEA_EXCLUIDA,
                referencia=linea.codigo_referencia,
                motivo=linea.motivo_exclusion))
    if esperado is not None and esperado != linea.pedido_final:
        raise ErrorCorrida(
            codigos.E_CORRIDA_EDICION_DESACTUALIZADA,
            codigos.mensaje(
                codigos.E_CORRIDA_EDICION_DESACTUALIZADA,
                actual=linea.pedido_final))


async def _leer_linea(db, corrida_id: UUID, linea_id: int, *, bloquear):
    consulta = select(CorridaLinea).where(
        CorridaLinea.id == linea_id, CorridaLinea.corrida_id == corrida_id)
    if bloquear:
        consulta = consulta.with_for_update().execution_options(
            populate_existing=True)
    linea = (await db.execute(consulta)).scalars().first()
    if linea is None:
        raise LookupError("Línea no encontrada.")
    return linea


async def totales_de_tienda(
    db, corrida_id: UUID, sucursal_id: UUID,
) -> Dict[str, Decimal]:
    """Unidades y valor a pedir y sugeridos de la tienda (sin excluidas)."""
    cl = CorridaLinea
    sugerido = func.round(
        cl.pedido_sugerido * func.coalesce(cl.precio, 0), 2)
    fila = (await db.execute(
        select(
            func.coalesce(func.sum(cl.pedido_final), 0),
            func.coalesce(func.sum(cl.valor_pedido), 0),
            func.coalesce(func.sum(cl.pedido_sugerido), 0),
            func.coalesce(func.sum(sugerido), 0))
        .where(cl.corrida_id == corrida_id, cl.sucursal_id == sucursal_id,
               cl.motivo_exclusion.is_(None)))).first()
    claves = ("unidades_a_pedir", "valor_a_pedir", "unidades_sugerido",
              "valor_sugerido")
    return dict(zip(claves, (Decimal(v) for v in fila)))


async def _escribir(
    db, linea: Any, nueva: int, corrida_id: UUID, usuario_id: UUID,
) -> None:
    """UPDATE de la línea y, después (el padre antes que el hijo), la fila
    del historial; ambos en la transacción del llamador."""
    anterior = linea.pedido_final
    linea.pedido_final = Decimal(nueva).quantize(Decimal("0.01"))
    linea.valor_pedido = valores.valor(nueva, linea.precio)
    await db.flush()
    await db.execute(insert(CorridaLineaHistorial).values(
        corrida_id=corrida_id, linea_id=linea.id,
        sucursal_id=linea.sucursal_id, campo="pedido_final",
        valor_anterior=anterior, valor_nuevo=linea.pedido_final,
        motivo=MOTIVO_MANUAL, usuario_id=usuario_id))


async def editar_linea(
    db, corrida_id: UUID, linea_id: int, cantidad: Any,
    esperado: Optional[Decimal], usuario_id: UUID,
) -> ResultadoEdicion:
    """Pone `cantidad` como `pedido_final` de la línea.

    `LookupError` si la corrida o la línea no existen (la API responde 404);
    `ErrorCorrida` con el código de la regla que lo rechaza. La misma
    cantidad es un no-op: no escribe ni deja historial."""
    corrida = await bloqueos.bloquear_corrida(
        db, corrida_id, exclusivo=False)
    visto = await _leer_linea(db, corrida_id, linea_id, bloquear=False)
    bloqueos.exigir_operable(corrida, ACCION)
    tienda = await bloqueos.bloquear_tienda(
        db, corrida_id, visto.sucursal_id, exclusivo=False)
    _exigir_borrador(tienda)
    nueva = valores.validar_cantidad(cantidad)
    linea = await _leer_linea(db, corrida_id, linea_id, bloquear=True)
    _exigir_editable(linea, esperado)
    if linea.pedido_final != nueva:
        await _escribir(db, linea, nueva, corrida_id, usuario_id)
    ultima = (await consultas.ediciones_de(db, [linea.id])).get(linea.id)
    totales = await totales_de_tienda(db, corrida_id, linea.sucursal_id)
    return ResultadoEdicion(linea, ultima, totales)
