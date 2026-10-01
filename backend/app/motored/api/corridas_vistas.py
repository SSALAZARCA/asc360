"""
Motored Pedidos F4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B6, ADR-8
y ADR-9, decisiones F4-8 y F4-9): `/api/motored/corridas`, las vistas de la
RED sobre una corrida.

- `GET /{id}/consolidado`: la matriz referencias x tiendas con la cantidad a
  pedir y sus totales (CO-01..CO-11), paginada por referencia.
- `GET /{id}/comparar?con=<real_id>`: un escenario frente a su corrida real
  de la misma semana (SC-07..SC-13), paginada por (tienda, referencia).

Router delgado y de sólo lectura: las reglas y el SQL viven en
`services/corridas/{consolidado,comparacion}.py`; nada se escribe ni se
confirma. RBAC (F4-16): ADMIN y COMPRAS; el resto, 403. Las dos vistas
reciben `limite` de 1 a 100 (el consolidado y la comparación nunca devuelven
más de 100 filas por página).
"""
import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.api import corridas_comun as comun
from app.motored.deps import (
    MotoredUser,
    get_motored_db_or_503,
    require_motored_ready,
)
from app.motored.schemas.pedido import ComparacionRead, ConsolidadoRead
from app.motored.services.corridas import comparacion, consolidado
from app.motored.services.corridas.codigos import ErrorCorrida

PAGINA, PAGINA_MAX = 100, 100
ESTADOS_PEDIDO = Literal["BORRADOR", "CERRADO", "ENVIADO"]

router = APIRouter(
    prefix="/corridas",
    tags=["motored-corridas"],
    dependencies=[Depends(require_motored_ready)],
)


@router.get("/{corrida_id}/consolidado", response_model=ConsolidadoRead)
async def consolidado_corrida(
    corrida_id: uuid.UUID,
    q: Optional[str] = None,
    estado_pedido: Optional[ESTADOS_PEDIDO] = None,
    limite: int = Query(PAGINA, ge=1, le=PAGINA_MAX),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(comun.require_read),
):
    """La matriz de la corrida: una columna por tienda (con el estado de su
    pedido y su total sobre TODAS las referencias), una fila por referencia
    con algo que pedir (paginada) y los totales. `q` busca por código o
    nombre y sólo acota las filas; `estado_pedido` deja sólo las tiendas con
    ese estado."""
    cuerpo = await consolidado.consolidado(
        db, corrida_id, q=(q or "").strip() or None,
        estado_pedido=estado_pedido, limite=limite, offset=offset)
    if cuerpo is None:
        raise comun.no_existe()
    return cuerpo


@router.get("/{corrida_id}/comparar", response_model=ComparacionRead)
async def comparar_corrida(
    corrida_id: uuid.UUID,
    con: uuid.UUID,
    sucursal_id: Optional[uuid.UUID] = None,
    solo_diferencias: bool = False,
    limite: int = Query(PAGINA, ge=1, le=PAGINA_MAX),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(comun.require_read),
):
    """El escenario `{corrida_id}` frente a la corrida real `con` de la
    misma semana: lo sugerido de cada lado y su delta por (tienda,
    referencia), los totales por tienda y las tiendas que no se comparan.
    422 E-CORRIDA-063 si el emparejamiento no es válido."""
    try:
        cuerpo = await comparacion.comparar(
            db, corrida_id, con, sucursal_id=sucursal_id,
            solo_diferencias=solo_diferencias, limite=limite, offset=offset)
    except ErrorCorrida as error:
        raise comun.rechazo(error) from error
    if cuerpo is None:
        raise comun.no_existe()
    return cuerpo
