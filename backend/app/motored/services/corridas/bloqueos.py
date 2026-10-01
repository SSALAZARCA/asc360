"""
Motored Pedidos F4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B2,
ADR-3): bloqueos de fila y regla común de "corrida operable".

Orden global de bloqueos, siempre un prefijo de: cargas -> corrida ->
`corrida_sucursal` (la tienda) -> líneas. Cada operación por tienda toma la
corrida `FOR SHARE` (las tiendas distintas avanzan en paralelo y la anulación,
que la toma `FOR UPDATE`, espera a todas) y después SU tienda: `FOR SHARE` al
editar (varias ediciones a la vez; un cierre, que la toma `FOR UPDATE`, las
espera) o `FOR UPDATE` al cerrar, reabrir o enviar. Cerrar toma antes las
cargas vinculadas `FOR SHARE` (`cargas_anuladas`), igual que
`finalizar_corrida`, para que la guarda de anulación de cargas, que las toma
`FOR UPDATE`, nunca se cruce con un cierre.

Ningún commit acá: la transacción es del llamador.
"""
from typing import Any, List, Optional, Sequence
from uuid import UUID

from sqlalchemy import select

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.corrida import Corrida
from app.motored.models.corrida_carga import CorridaCarga
from app.motored.models.corrida_sucursal import CorridaSucursal
from app.motored.models.sucursal import Sucursal
from app.motored.services.corridas import codigos, estados
from app.motored.services.corridas.codigos import ErrorCorrida


async def bloquear_corrida(db, corrida_id: UUID, *, exclusivo: bool):
    """La corrida con su fila bloqueada (`FOR UPDATE` si `exclusivo`, si no
    `FOR SHARE`). `LookupError` si no existe."""
    resultado = await db.execute(
        select(Corrida).where(Corrida.id == corrida_id)
        .with_for_update(read=not exclusivo)
        .execution_options(populate_existing=True))
    corrida = resultado.scalars().first()
    if corrida is None:
        raise LookupError("Corrida no encontrada.")
    return corrida


async def bloquear_tienda(
    db, corrida_id: UUID, sucursal_id: UUID, *, exclusivo: bool,
):
    """La fila `corrida_sucursal` de la tienda, bloqueada. `LookupError` si
    la tienda no está en la corrida."""
    resultado = await db.execute(
        select(CorridaSucursal)
        .where(CorridaSucursal.corrida_id == corrida_id,
               CorridaSucursal.sucursal_id == sucursal_id)
        .with_for_update(read=not exclusivo)
        .execution_options(populate_existing=True))
    tienda = resultado.scalars().first()
    if tienda is None:
        raise LookupError("La tienda no está en la corrida.")
    return tienda


async def bloquear_tiendas(
    db, corrida_id: UUID, sucursal_ids: Optional[Sequence[UUID]],
) -> list:
    """`[(tienda, nombre)]` con las filas bloqueadas `FOR UPDATE` en orden de
    `sucursal_id` (el mismo orden en todos los lotes: sin deadlock). Sin
    lista, todas las tiendas OK; con lista, exactamente esas (`LookupError`
    si alguna no está en la corrida)."""
    cs = CorridaSucursal
    consulta = (
        select(cs, Sucursal.nombre)
        .join(Sucursal, Sucursal.id == cs.sucursal_id)
        .where(cs.corrida_id == corrida_id))
    if sucursal_ids is None:
        consulta = consulta.where(cs.estado == estados.SUC_OK)
    else:
        consulta = consulta.where(cs.sucursal_id.in_(list(sucursal_ids)))
    filas = (await db.execute(
        consulta.order_by(cs.sucursal_id)
        .with_for_update(of=cs)
        .execution_options(populate_existing=True))).all()
    if sucursal_ids is not None and len(filas) != len(set(sucursal_ids)):
        raise LookupError("La tienda no está en la corrida.")
    return filas


async def cargas_anuladas(db, corrida_id: UUID) -> List[UUID]:
    """Bloquea `FOR SHARE` TODAS las cargas vinculadas (una anulación
    concurrente espera) y devuelve las que están ANULADO."""
    resultado = await db.execute(
        select(CargaArchivo.id, CargaArchivo.estado)
        .join(CorridaCarga, CorridaCarga.carga_id == CargaArchivo.id)
        .where(CorridaCarga.corrida_id == corrida_id)
        .with_for_update(read=True, of=CargaArchivo))
    return [
        fila[0] for fila in resultado.all()
        if fila[1] == estados.ESTADO_CARGA_ANULADO]


def exigir_operable(
    corrida: Any, accion: str, *, permite_invalidada: bool = False,
) -> None:
    """La corrida admite una acción sobre el pedido de una tienda.

    Orden: escenario (E-CORRIDA-042, que dice la `accion`), cálculo no
    terminado o anulada (040) e invalidada por una carga anulada (041).
    `permite_invalidada` es para reabrir: devolver un pedido a BORRADOR
    nunca es riesgoso y es lo que deja anular la carga."""
    if corrida.es_escenario:
        raise ErrorCorrida(
            codigos.E_CORRIDA_ESCENARIO_NO_SE_CIERRA,
            codigos.mensaje_escenario(accion))
    if corrida.estado not in estados.CALCULADAS:
        raise ErrorCorrida(
            codigos.E_CORRIDA_ESTADO_NO_ADMITE,
            codigos.mensaje(
                codigos.E_CORRIDA_ESTADO_NO_ADMITE, estado=corrida.estado))
    if corrida.invalidada and not permite_invalidada:
        raise ErrorCorrida(
            codigos.E_CORRIDA_INVALIDADA,
            codigos.mensaje(codigos.E_CORRIDA_INVALIDADA))
