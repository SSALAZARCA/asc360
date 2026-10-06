"""
Motored: `GET /api/motored/inicio`, the data of the welcome page.

Returns the sections of the caller's role (`services/inicio.py`); each one
answers `{"disponible": false}` on its own failure instead of failing the
page. Read only. RBAC: ADMIN, COMPRAS, GERENCIA and SERVICIO_CLIENTE; the
last two are path-confined, so `/api/motored/inicio` is in their allow-lists
(`deps.py`). SUCURSAL and CONSULTA get the central 403.
"""
from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.deps import (
    MotoredUser,
    get_motored_db_or_503,
    require_motored_ready,
    require_roles,
)
from app.motored.services import inicio

ROLES_INICIO = ("ADMIN", "COMPRAS", "GERENCIA", "SERVICIO_CLIENTE")

router = APIRouter(
    prefix="/inicio",
    tags=["motored-inicio"],
    dependencies=[Depends(require_motored_ready)],
)


@router.get("")
async def leer_inicio(
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(require_roles(*ROLES_INICIO)),
) -> Dict[str, Any]:
    """`{rol, hoy, secciones: {nombre: {disponible, ...}}}`."""
    return await inicio.construir_inicio(db, user.role)
