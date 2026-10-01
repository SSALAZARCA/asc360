"""
Motored Pedidos F4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B2, B3a y
B4, ADR-1, ADR-3): lecturas del pedido de cada tienda.

Sólo SELECTs, nunca un commit. Las cifras a pedir y sugeridas de una tienda
(`totales_de_tienda`, que la edición también devuelve), el último evento de
pedido de cada tienda (`ultimos_eventos`), el envío de cada tienda ENVIADO
(`envios_de`, B4), la cabecera de la pantalla de una tienda
(`cabecera_tienda`) y su línea de tiempo (`eventos_tienda`). El
alcance por sucursal es defensa en profundidad: `alcance` es `None` o el
conjunto de sucursales visibles y restringe cada consulta en SQL; lo que no
se ve responde `None` (la API lo trata como 404). Armar las respuestas es de
`proyecciones.py` (puro).
"""
from decimal import Decimal
from typing import Any, Dict, FrozenSet, List, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on

from app.motored.models.corrida import Corrida
from app.motored.models.corrida_envio import CorridaEnvio
from app.motored.models.corrida_linea import CorridaLinea
from app.motored.models.corrida_sucursal import CorridaSucursal
from app.motored.models.pedido_evento import PedidoEvento
from app.motored.models.sucursal import Sucursal
from app.motored.models.usuario import Usuario
from app.motored.services.corridas import estados, proyecciones

Alcance = Optional[FrozenSet[UUID]]


def _en_alcance(columna, alcance: Alcance) -> list:
    return [] if alcance is None else [columna.in_(sorted(alcance))]


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


async def ultimos_eventos(
    db, corrida_id: UUID, alcance: Alcance,
    sucursal_id: Optional[UUID] = None,
) -> Dict[UUID, proyecciones.UltimoEvento]:
    """El último evento de pedido de cada tienda de la corrida (o de UNA),
    en una sola consulta `DISTINCT ON`. Una tienda sin eventos no aparece.
    `usuario` es `None` en los cierres que migró F3."""
    e = PedidoEvento
    condiciones = [
        e.corrida_id == corrida_id, *_en_alcance(e.sucursal_id, alcance)]
    if sucursal_id is not None:
        condiciones.append(e.sucursal_id == sucursal_id)
    filas = await db.execute(
        select(e.sucursal_id, e.evento, Usuario.nombre, e.creado_en)
        .outerjoin(Usuario, Usuario.id == e.usuario_id)
        .where(*condiciones)
        .ext(distinct_on(e.sucursal_id))
        .order_by(e.sucursal_id, e.creado_en.desc(), e.id.desc()))
    return {
        fila[0]: proyecciones.UltimoEvento(fila[1], fila[2], fila[3])
        for fila in filas.all()}


async def envios_de(
    db, corrida_id: UUID, alcance: Alcance,
    sucursal_id: Optional[UUID] = None,
) -> Dict[UUID, proyecciones.EnvioTienda]:
    """El envío de cada tienda de la corrida (o de UNA) que ya se envió: su
    número de orden, la fecha, quién (el nombre) y cuándo, en una sola
    consulta. Una tienda sin envío no aparece (`ENVIADO <=> existe la fila`,
    por eso quien llama sólo pregunta si alguna está ENVIADO)."""
    ce = CorridaEnvio
    condiciones = [
        ce.corrida_id == corrida_id, *_en_alcance(ce.sucursal_id, alcance)]
    if sucursal_id is not None:
        condiciones.append(ce.sucursal_id == sucursal_id)
    filas = await db.execute(
        select(ce.sucursal_id, ce.numero_pedido_proveedor, ce.fecha_envio,
               Usuario.nombre, ce.enviada_en)
        .outerjoin(Usuario, Usuario.id == ce.enviada_por)
        .where(*condiciones))
    return {
        fila[0]: proyecciones.EnvioTienda(*fila[1:]) for fila in filas.all()}


async def cabecera_tienda(
    db, corrida_id: UUID, sucursal_id: UUID, alcance: Alcance,
) -> Optional[Dict[str, Any]]:
    """La cabecera de la pantalla del pedido de UNA tienda; `None` si la
    corrida no existe, la tienda no está en ella o no es visible."""
    cs = CorridaSucursal
    fila = (await db.execute(
        select(Corrida, cs, Sucursal.nombre, Sucursal.sic)
        .join(cs, cs.corrida_id == Corrida.id)
        .join(Sucursal, Sucursal.id == cs.sucursal_id)
        .where(Corrida.id == corrida_id, cs.sucursal_id == sucursal_id,
               *_en_alcance(cs.sucursal_id, alcance)))).first()
    if fila is None:
        return None
    corrida, tienda, nombre, sic = fila
    totales = await totales_de_tienda(db, corrida_id, sucursal_id)
    ultimo = (await ultimos_eventos(
        db, corrida_id, alcance, sucursal_id)).get(sucursal_id)
    envio = None
    if tienda.estado_pedido == estados.PEDIDO_ENVIADO:
        envio = (await envios_de(
            db, corrida_id, alcance, sucursal_id)).get(sucursal_id)
    return proyecciones.cabecera_tienda(
        corrida, tienda, nombre, sic, totales, ultimo, envio)


async def eventos_tienda(
    db, corrida_id: UUID, sucursal_id: UUID, alcance: Alcance,
) -> Optional[List[Dict[str, Any]]]:
    """La línea de tiempo del pedido de una tienda, el evento más antiguo
    primero; `None` si la tienda no está en la corrida o no es visible."""
    cs = CorridaSucursal
    existe = await db.execute(
        select(cs.sucursal_id).where(
            cs.corrida_id == corrida_id, cs.sucursal_id == sucursal_id,
            *_en_alcance(cs.sucursal_id, alcance)))
    if existe.scalars().first() is None:
        return None
    e = PedidoEvento
    filas = await db.execute(
        select(e.id, e.evento, e.motivo, e.detalle, e.usuario_id,
               Usuario.nombre, e.creado_en)
        .outerjoin(Usuario, Usuario.id == e.usuario_id)
        .where(e.corrida_id == corrida_id, e.sucursal_id == sucursal_id)
        .order_by(e.creado_en.asc(), e.id.asc()))
    claves = ("id", "evento", "motivo", "detalle", "usuario_id", "usuario",
              "creado_en")
    return [dict(zip(claves, fila)) for fila in filas.all()]
