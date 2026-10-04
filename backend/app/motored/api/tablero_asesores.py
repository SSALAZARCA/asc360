"""
Tablero de asesores (feature motored-tablero-asesores, T4): GET del tablero.

Router propio y SOLO ADMIN|COMPRAS|GERENCIA: nunca comparte permisos ni rutas con
`/corridas*`. Contiene datos personales (nombres de vendedores, Ley 1581): no
hay acceso para otros roles.

`GET /tablero-asesores?desde=AAAA-MM&hasta=AAAA-MM&hmcl=incluir|excluir|solo`
`GET /tablero-asesores?meses=AAAA-MM,AAAA-MM&sucursales=uuid,uuid&hmcl=...`

`meses` (lista, no tienen que ser consecutivos) y `desde`/`hasta` (rango) son
excluyentes; `sucursales` es opcional (sin ella, todas).
"""
import uuid
from typing import Any, Dict, List, Optional

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

_require_rol = require_roles("ADMIN", "COMPRAS", "GERENCIA")

_MES = r"^\d{4}-(0[1-9]|1[0-2])$"


def _error_422(detalle: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detalle)


def _sucursales(texto: Optional[str]) -> Optional[List[uuid.UUID]]:
    if texto is None:
        return None
    ids: List[uuid.UUID] = []
    for crudo in texto.split(","):
        try:
            ids.append(uuid.UUID(crudo.strip()))
        except ValueError:
            raise _error_422(f"Sucursal inválida: '{crudo}'.")
    return list(dict.fromkeys(ids))


@router.get("")
async def obtener_tablero(
    desde: Optional[str] = Query(None, pattern=_MES, description="Mes inicial, AAAA-MM"),
    hasta: Optional[str] = Query(None, pattern=_MES, description="Mes final, AAAA-MM"),
    meses: Optional[str] = Query(None, description="Meses AAAA-MM separados por coma (maximo 12)"),
    sucursales: Optional[str] = Query(None, description="Ids de sucursal separados por coma; sin ella, todas"),
    hmcl: str = Query(HMCL_INCLUIR, pattern="^(incluir|excluir|solo)$"),
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_rol),
) -> Dict[str, Any]:
    if meses is not None and (desde is not None or hasta is not None):
        raise _error_422("Use 'meses' o 'desde' y 'hasta', no ambos.")
    if meses is None and (desde is None or hasta is None):
        raise _error_422("Indique 'meses' o 'desde' y 'hasta'.")
    ids = _sucursales(sucursales)
    # El rango y los `desde`/`hasta` sin sucursales siguen el camino de siempre
    # (`calcular_tablero(db, desde, hasta, hmcl)`); solo se agrega lo nuevo si se pidio.
    extra = {} if ids is None else {"sucursal_ids": ids}
    try:
        if meses is not None:
            return await consultas.calcular_tablero_por_meses(db, meses.split(","), hmcl, ids)
        return await consultas.calcular_tablero(db, desde, hasta, hmcl, **extra)
    except ValueError as exc:
        raise _error_422(str(exc))
