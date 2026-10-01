"""
Tablero de asesores (feature motored-tablero-asesores, T4): indicadores de
venta por asesor de repuestos, calculados desde `venta_detalle`.

Router propio y SOLO ADMIN|COMPRAS: nunca comparte permisos ni rutas con
`/corridas*`. Contiene datos personales (nombres de vendedores, Ley 1581): no
hay vista por sucursal ni acceso para otros roles.

`GET /tablero-asesores?desde=AAAA-MM&hasta=AAAA-MM&hmcl=incluir|excluir|solo`
"""
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.deps import MotoredUser, get_motored_db_or_503, require_motored_ready, require_roles
from app.motored.services import tablero_asesores_consultas as consultas
from app.motored.services.tablero_asesores import HMCL_INCLUIR

router = APIRouter(
    prefix="/tablero-asesores",
    tags=["motored-tablero-asesores"],
    dependencies=[Depends(require_motored_ready)],
)

_require_rol = require_roles("ADMIN", "COMPRAS")

_MES = r"^\d{4}-(0[1-9]|1[0-2])$"


@router.get("")
async def obtener_tablero(
    desde: str = Query(..., pattern=_MES, description="Mes inicial, AAAA-MM"),
    hasta: str = Query(..., pattern=_MES, description="Mes final, AAAA-MM"),
    hmcl: str = Query(HMCL_INCLUIR, pattern="^(incluir|excluir|solo)$"),
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_rol),
) -> Dict[str, Any]:
    try:
        return await consultas.calcular_tablero(db, desde, hasta, hmcl)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
