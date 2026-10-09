"""
Motored: `/api/motored/gestion-repuestos/ingresos-facturas`, the invoices
still waiting for an ingreso (odd/tasks/motored-ingresos-pendientes.md, P1).

Panel reads (ADMIN, COMPRAS, GERENCIA, COORDINADOR_REPUESTOS):
- `GET /`: `{verificable_desde, resumen}` (pendientes, llegaron_sin_ingresar,
  sin_confirmar, aun_no_llegan, mas_antigua, valor_pendiente).
- `GET /por-tienda`: `{verificable_desde, tiendas}`, one row per principal
  store, most pending first.
- `GET /detalle?sucursal=&estado=&min_dias=`: `{verificable_desde, items}`,
  oldest first.
- `GET /historial?factura=&sucursal=`: who changed the confirmation, when.
- `GET /asesor?sucursal=`: the `pendientes_ingreso` block of one store, for
  the asesor card.
`verificable_desde` is null when no ingreso is loaded yet (nothing can be
verified: every list is empty).

`POST /confirmar` `{factura, sucursal_id, estado}`: "LLEGO" | "NO_HA_LLEGADO".
ONLY COORDINADOR_REPUESTOS (the other panel roles read; asesores confirm
through the public link). 409 when the invoice is no longer pending.
"""
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.deps import (
    MotoredUser,
    get_current_motored_user,
    get_motored_db_or_503,
    require_motored_ready,
    require_roles,
)
from app.motored.models.usuario import Usuario
from app.motored.services import ingresos_pendientes as ingresos
from app.motored.services import sucursal_grupo

# TODO(pedidos): COORDINADOR_REPUESTOS is created by the pedidos session; the
# role compares as a plain string, so listing it here is harmless meanwhile.
# Path confinement for GERENCIA / COORDINADOR_REPUESTOS lives in `deps.py`.
ROLES_PANEL = ("ADMIN", "COMPRAS", "GERENCIA", "COORDINADOR_REPUESTOS")
ROL_CONFIRMA = "COORDINADOR_REPUESTOS"
MSG_ESTADO_FILTRO = "El estado del filtro no es válido."

router = APIRouter(
    prefix="/gestion-repuestos/ingresos-facturas",
    tags=["motored-ingresos-facturas"],
    dependencies=[Depends(require_motored_ready)],
)

_panel = Depends(require_roles(*ROLES_PANEL))


class ConfirmarIn(BaseModel):
    factura: str
    sucursal_id: uuid.UUID
    estado: str


async def _items(
    db: AsyncSession, sucursal: Optional[uuid.UUID] = None,
) -> List[Dict[str, Any]]:
    return await ingresos.pendientes(db, None if sucursal is None else [sucursal])


@router.get("", dependencies=[_panel])
async def leer_resumen(db: AsyncSession = Depends(get_motored_db_or_503)) -> Dict[str, Any]:
    desde = await ingresos.verificable_desde(db)
    items = await _items(db) if desde else []
    return {"verificable_desde": desde, "resumen": ingresos.resumen(items)}


@router.get("/por-tienda", dependencies=[_panel])
async def leer_por_tienda(db: AsyncSession = Depends(get_motored_db_or_503)) -> Dict[str, Any]:
    desde = await ingresos.verificable_desde(db)
    items = await _items(db) if desde else []
    return {"verificable_desde": desde, "tiendas": ingresos.por_tienda(items)}


@router.get("/detalle", dependencies=[_panel])
async def leer_detalle(
    sucursal: Optional[uuid.UUID] = Query(None),
    estado: Optional[str] = Query(None),
    min_dias: Optional[int] = Query(None, ge=0),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> Dict[str, Any]:
    if estado is not None and estado not in (
            ingresos.SIN_CONFIRMAR, *ingresos.ESTADOS_CONFIRMABLES):
        raise HTTPException(status_code=422, detail=MSG_ESTADO_FILTRO)
    desde = await ingresos.verificable_desde(db)
    items = await _items(db, sucursal) if desde else []
    if estado is not None:
        items = [i for i in items if i["estado"] == estado]
    if min_dias is not None:
        items = [i for i in items if i["dias"] >= min_dias]
    return {"verificable_desde": desde, "items": items}


@router.get("/historial", dependencies=[_panel])
async def leer_historial(
    factura: str = Query(...), sucursal: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> Dict[str, Any]:
    clave = ingresos.parsear_factura(factura)
    if clave is None:
        raise HTTPException(status_code=422, detail=ingresos.MSG_FACTURA)
    principal = await sucursal_grupo.principal_de(db)
    return {"historial": await ingresos.historial(
        db, clave, principal.get(sucursal, sucursal))}


@router.get("/asesor", dependencies=[_panel])
async def leer_de_asesor(
    sucursal: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> Dict[str, Any]:
    return await ingresos.para_asesor(db, [sucursal])


@router.post("/confirmar", dependencies=[Depends(require_roles(ROL_CONFIRMA))])
async def confirmar(
    cuerpo: ConfirmarIn,
    user: MotoredUser = Depends(get_current_motored_user),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> Dict[str, Any]:
    usuario = (await db.execute(
        select(Usuario).where(Usuario.id == uuid.UUID(str(user.user_id)))
    )).scalars().first()
    if usuario is None:
        raise HTTPException(status_code=403, detail="No tiene permisos para realizar esta acción.")
    actor = ingresos.Actor(
        nombre=usuario.nombre, usuario_id=usuario.id,
        cedula=usuario.cedula if usuario.cedula_aprobada else None)
    try:
        return await ingresos.confirmar(
            db, cuerpo.factura, cuerpo.sucursal_id, cuerpo.estado, actor, "web")
    except ingresos.PendienteError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
