"""
CLIENTES TECNIRED (feature motored-tablero-asesores, T2): consulta de la lista
vigente. La CARGA vive en el router generico de maestros
(`/maestros/cliente_tecnired/carga...` y `/plantilla.xlsx`): todo-o-nada, y cada
carga reemplaza la lista completa.

Dato personal (Ley 1581): NIT y razon social de clientes. Solo ADMIN y COMPRAS,
los mismos roles que pueden cargar la lista.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.deps import MotoredUser, get_motored_db_or_503, require_motored_ready, require_roles
from app.motored.models.cliente_tecnired import ClienteTecnired
from app.motored.schemas.cliente_tecnired import ClienteTecniredRead, normalizar_nit

router = APIRouter(
    prefix="/clientes-tecnired",
    tags=["motored-clientes-tecnired"],
    dependencies=[Depends(require_motored_ready)],
)

_require_rol = require_roles("ADMIN", "COMPRAS")

PAGE_SIZE_DEFAULT = 50
PAGE_SIZE_MAX = 200


def _filtro_busqueda(q: Optional[str]):
    texto = (q or "").strip()
    if not texto:
        return None
    patron = f"%{texto}%"
    nit = normalizar_nit(texto)
    return or_(ClienteTecnired.nit.ilike(f"%{nit}%"), ClienteTecnired.razon_social.ilike(patron))


@router.get("")
async def listar_clientes_tecnired(
    page: int = Query(1, ge=1),
    page_size: int = Query(PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX),
    q: Optional[str] = None,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_rol),
) -> dict:
    filtro = _filtro_busqueda(q)
    consulta_total = select(func.count()).select_from(ClienteTecnired)
    consulta = select(ClienteTecnired).order_by(ClienteTecnired.nit)
    if filtro is not None:
        consulta_total = consulta_total.where(filtro)
        consulta = consulta.where(filtro)

    total = (await db.execute(consulta_total)).scalars().first() or 0
    filas = (
        await db.execute(consulta.offset((page - 1) * page_size).limit(page_size))
    ).scalars().all()
    return {
        "items": [ClienteTecniredRead.model_validate(f).model_dump(mode="json") for f in filas],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
