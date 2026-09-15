"""
Motored Pedidos — router del tablero de salud de maestros
(sdd/motored-pedidos-cimientos, Fase 4, §7.12). Solo lectura -- ninguna
capacidad de escritura existe en esta capacidad, así que CUALQUIER rol
autenticado puede consultarla.

Vive bajo `/maestros/salud` (design doc, sección Interfaces) -- por eso
tiene el MISMO número de segmentos de path que `GET /maestros/{entidad}`
(el router genérico de `maestros.py`). `router.py` debe incluir este router
ANTES que `maestros.py` para que Starlette no intercepte `/maestros/salud`
como `entidad="salud"` (ver comentario en `router.py`).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.deps import MotoredUser, get_current_motored_user, get_motored_db_or_503, require_motored_ready
from app.motored.schemas.salud import SaludMaestros
from app.motored.services.salud import evaluar_salud

router = APIRouter(
    prefix="/maestros/salud",
    tags=["motored-salud"],
    dependencies=[Depends(require_motored_ready)],
)


@router.get("", response_model=SaludMaestros)
async def salud(
    db: AsyncSession = Depends(get_motored_db_or_503),
    _user: MotoredUser = Depends(get_current_motored_user),
):
    return await evaluar_salud(db)
