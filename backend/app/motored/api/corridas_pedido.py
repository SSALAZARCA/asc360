"""
Motored Pedidos F4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B2, ADR-3):
`/api/motored/corridas`, escrituras y lecturas del pedido por tienda.

Por ahora trae la edición de una línea (`PATCH /{id}/lineas/{linea_id}`) y su
historial. Las acciones por tienda (cerrar, reabrir, enviar, exportar,
recorte) llegan en las siguientes rebanadas. Router delgado: las reglas viven
en `services/corridas/edicion.py` y las lecturas en `consultas.py`.

RBAC (F4-16): ADMIN y COMPRAS; el resto, 403. Los servicios no hacen commit:
acá se confirma o se deshace.
"""
import uuid
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.api import corridas_comun as comun
from app.motored.deps import (
    MotoredUser,
    get_motored_db_or_503,
    require_motored_ready,
)
from app.motored.schemas.pedido import (
    HistorialLinea,
    LineaEditada,
    LineaEditar,
    TotalesTienda,
)
from app.motored.services.corridas import consultas, edicion
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
