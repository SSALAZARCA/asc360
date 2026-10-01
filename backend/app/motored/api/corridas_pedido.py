"""
Motored Pedidos F4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B2 y B3a,
ADR-1, ADR-3): `/api/motored/corridas`, escrituras y lecturas del pedido por
tienda.

Trae la edición de una línea (`PATCH /{id}/lineas/{linea_id}`) y su
historial (B2); y el ciclo de vida por tienda (B3a): cerrar varias a la vez
(`POST /{id}/cerrar`, ahora por lote), cerrar y reabrir UNA, la cabecera de
la tienda y su línea de tiempo. Enviar, exportar y recortar llegan en las
siguientes rebanadas. Router delgado: las reglas viven en
`services/corridas/` (`edicion`, `pedido_tienda`) y las lecturas en
`consultas` y `lecturas_pedido`.

RBAC (F4-16): ADMIN y COMPRAS; el resto, 403. Los servicios no hacen commit:
`comun.ejecutar` confirma o deshace.
"""
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.api import corridas_comun as comun
from app.motored.deps import (
    MotoredUser,
    get_motored_db_or_503,
    require_motored_ready,
)
from app.motored.schemas.pedido import (
    CabeceraTienda,
    CerrarLote,
    CierreLote,
    EstadoPedidoTienda,
    EventoPedido,
    HistorialLinea,
    LineaEditada,
    LineaEditar,
    ReabrirCuerpo,
    TotalesTienda,
)
from app.motored.services.corridas import (
    consultas,
    edicion,
    lecturas_pedido,
    pedido_tienda,
)
from app.motored.services.corridas.codigos import ErrorCorrida

router = APIRouter(
    prefix="/corridas",
    tags=["motored-corridas"],
    dependencies=[Depends(require_motored_ready)],
)


@router.patch("/{corrida_id}/lineas/{linea_id}", response_model=LineaEditada)
async def editar_linea(
    corrida_id: uuid.UUID,
    linea_id: int,
    cuerpo: LineaEditar,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(comun.require_write),
):
    """Cambia la cantidad a pedir de una línea de un pedido en BORRADOR y
    deja su historial. 404 si no existe, 409/422 con el código de la regla."""
    try:
        resultado = await edicion.editar_linea(
            db, corrida_id, linea_id, cuerpo.pedido_final, cuerpo.esperado,
            uuid.UUID(user.user_id))
    except LookupError as error:
        await db.rollback()
        raise comun.no_existe(str(error)) from error
    except ErrorCorrida as error:
        await db.rollback()
        raise comun.rechazo(error) from error
    await db.commit()
    return LineaEditada(
        linea=comun.linea_read(resultado.linea, resultado.ultima_edicion),
        totales_tienda=TotalesTienda(**resultado.totales_tienda))


@router.get(
    "/{corrida_id}/lineas/{linea_id}/historial",
    response_model=List[HistorialLinea])
async def historial_de_linea(
    corrida_id: uuid.UUID,
    linea_id: int,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(comun.require_read),
):
    """Las ediciones de la línea, la más antigua primero."""
    filas = await consultas.historial_linea(db, corrida_id, linea_id)
    if filas is None:
        raise comun.no_existe("Línea no encontrada.")
    return filas


# --- Ciclo de vida del pedido por tienda (B3a) ------------------------------


@router.post("/{corrida_id}/cerrar", response_model=CierreLote)
async def cerrar_corrida(
    corrida_id: uuid.UUID,
    cuerpo: Optional[CerrarLote] = None,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(comun.require_write),
):
    """Cierra el pedido de varias tiendas, todo o nada: las nombradas en
    `sucursal_ids` o, sin cuerpo, todas las que sigan en BORRADOR. La corrida
    no cambia de estado."""
    ids = None if cuerpo is None else cuerpo.sucursal_ids
    resultado = await comun.ejecutar(db, pedido_tienda.cerrar_todas(
        db, corrida_id, uuid.UUID(user.user_id), ids))
    corrida = resultado.corrida
    return CierreLote(
        id=corrida.id, codigo=corrida.codigo, estado=corrida.estado,
        cerradas=resultado.cerradas, ya_cerradas=resultado.ya_cerradas)


def _estado_pedido(tienda) -> EstadoPedidoTienda:
    return EstadoPedidoTienda(
        corrida_id=tienda.corrida_id, sucursal_id=tienda.sucursal_id,
        estado_pedido=tienda.estado_pedido)


@router.post(
    "/{corrida_id}/sucursales/{sucursal_id}/cerrar",
    response_model=EstadoPedidoTienda)
async def cerrar_tienda(
    corrida_id: uuid.UUID,
    sucursal_id: uuid.UUID,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(comun.require_write),
):
    """BORRADOR -> CERRADO en una tienda."""
    return _estado_pedido(await comun.ejecutar(
        db, pedido_tienda.cerrar_tienda(
            db, corrida_id, sucursal_id, uuid.UUID(user.user_id))))


@router.post(
    "/{corrida_id}/sucursales/{sucursal_id}/reabrir",
    response_model=EstadoPedidoTienda)
async def reabrir_tienda(
    corrida_id: uuid.UUID,
    sucursal_id: uuid.UUID,
    cuerpo: ReabrirCuerpo = ReabrirCuerpo(),
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(comun.require_write),
):
    """CERRADO -> BORRADOR en una tienda, con un motivo obligatorio (el
    servicio lo valida: E-CORRIDA-046)."""
    return _estado_pedido(await comun.ejecutar(
        db, pedido_tienda.reabrir_tienda(
            db, corrida_id, sucursal_id, uuid.UUID(user.user_id),
            cuerpo.motivo)))


@router.get(
    "/{corrida_id}/sucursales/{sucursal_id}",
    response_model=CabeceraTienda)
async def cabecera_de_tienda(
    corrida_id: uuid.UUID,
    sucursal_id: uuid.UUID,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(comun.require_read),
):
    """La cabecera del pedido de una tienda: estado, cifras a pedir y
    sugeridas, último evento y acciones permitidas."""
    cuerpo = await lecturas_pedido.cabecera_tienda(
        db, corrida_id, sucursal_id, comun.alcance_de(user))
    if cuerpo is None:
        raise comun.no_existe("La tienda no está en la corrida.")
    return cuerpo


@router.get(
    "/{corrida_id}/sucursales/{sucursal_id}/eventos",
    response_model=List[EventoPedido])
async def eventos_de_tienda(
    corrida_id: uuid.UUID,
    sucursal_id: uuid.UUID,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(comun.require_read),
):
    """La línea de tiempo del pedido de una tienda, el más antiguo primero."""
    eventos = await lecturas_pedido.eventos_tienda(
        db, corrida_id, sucursal_id, comun.alcance_de(user))
    if eventos is None:
        raise comun.no_existe("La tienda no está en la corrida.")
    return eventos
