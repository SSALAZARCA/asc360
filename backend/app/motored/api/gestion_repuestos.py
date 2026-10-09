"""
Motored: `/api/motored/gestion-repuestos/ingresos-facturas`, the invoices
still waiting for an ingreso (odd/tasks/motored-ingresos-pendientes.md, P1).

Panel reads (ADMIN, COMPRAS, GERENCIA, COORDINADOR_REPUESTOS,
ANALISTA_ADMINISTRATIVO). Every item also carries `num_referencias`,
`responsable` ("ASESOR" up to the Configuración threshold, else "ANALISTA")
and `puede_descargar_plantilla` (analyst invoice confirmed "LLEGO"):
- `GET /`: `{verificable_desde, resumen}` (pendientes, llegaron_sin_ingresar,
  sin_confirmar, aun_no_llegan, mas_antigua, valor_pendiente).
- `GET /por-tienda`: `{verificable_desde, tiendas}`, one row per principal
  store, most pending first.
- `GET /detalle?sucursal=&estado=&min_dias=&max_dias=`: `{verificable_desde, items}`,
  oldest first.
- `GET /historial?factura=&sucursal=`: who changed the confirmation, when.
- `GET /asesor?sucursal=`: the `pendientes_ingreso` block of one store, for
  the asesor card.
`verificable_desde` is null when no ingreso is loaded yet (nothing can be
verified: every list is empty).

`POST /confirmar` `{factura, sucursal_id, estado}`: "LLEGO" | "NO_HA_LLEGADO".
ADMIN, COORDINADOR_REPUESTOS and ANALISTA_ADMINISTRATIVO (COMPRAS and
GERENCIA only read; asesores confirm through the public link). 409 when the
invoice is no longer pending.

`GET /plantilla?factura=&sucursal=` (ADMIN, ANALISTA_ADMINISTRATIVO): the ERP
"Entradas x Compra" .xlsx of an analyst invoice confirmed "LLEGO". 404 not
pending, 409 asesor invoice / not arrived / store without bodega principal.

Pending store transfers (`/gestion-repuestos/traslados`,
odd/tasks/motored-traslados-pendientes.md, T2), same roles as the invoices
(reads: `ROLES_PANEL`; confirm: `ROLES_CONFIRMA`). A transfer is the group
(`documento`, `bodega_salida`) of the latest applied TRASLADOS load:
- `GET /traslados`: `{ultima_carga, resumen}` (pendientes, recibidos_sin_erp,
  sin_confirmar, aun_no_llegan, mas_antiguo {documento, tienda, dias}, lineas).
- `GET /traslados/por-tienda`: `{ultima_carga, tiendas}`, receiving stores,
  most "recibidos" first.
- `GET /traslados/detalle?sucursal=&estado=&min_dias=&max_dias=`:
  `{ultima_carga, items}`, oldest first; `estado` is SIN_CONFIRMAR | RECIBIDO |
  NO_HA_LLEGADO.
- `GET /traslados/historial?documento=&bodega_salida=`: `{historial}`.
- `GET /traslados/asesor?sucursal=`: `{ultima_carga, items, resumen}` of one
  receiving store, for the asesor card.
- `POST /traslados/confirmar` `{documento, bodega_salida, estado}`:
  "RECIBIDO" | "NO_HA_LLEGADO"; 404 when the transfer is not in the current
  snapshot (any more).
"""
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
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
from app.motored.services import ingresos_plantilla as plantilla
from app.motored.services import traslados_pendientes as traslados
from app.motored.services.reloj import hoy_bogota
from app.motored.services import sucursal_grupo

# Path confinement for GERENCIA / COORDINADOR_REPUESTOS /
# ANALISTA_ADMINISTRATIVO lives in `deps.py`.
ROLES_PANEL = ("ADMIN", "COMPRAS", "GERENCIA", "COORDINADOR_REPUESTOS",
               "ANALISTA_ADMINISTRATIVO")
ROLES_CONFIRMA = ("ADMIN", "COORDINADOR_REPUESTOS", "ANALISTA_ADMINISTRATIVO")
ROLES_PLANTILLA = ("ADMIN", "ANALISTA_ADMINISTRATIVO")
MSG_ESTADO_FILTRO = "El estado del filtro no es válido."
MSG_RANGO_DIAS = "El mínimo de días no puede superar al máximo."

router_ingresos = APIRouter(
    prefix="/ingresos-facturas", tags=["motored-ingresos-facturas"])
router_traslados = APIRouter(
    prefix="/traslados", tags=["motored-traslados"])

_panel = Depends(require_roles(*ROLES_PANEL))


class ConfirmarIn(BaseModel):
    factura: str
    sucursal_id: uuid.UUID
    estado: str


async def _items(
    db: AsyncSession, sucursal: Optional[uuid.UUID] = None,
) -> List[Dict[str, Any]]:
    return await ingresos.pendientes(db, None if sucursal is None else [sucursal])


@router_ingresos.get("", dependencies=[_panel])
async def leer_resumen(db: AsyncSession = Depends(get_motored_db_or_503)) -> Dict[str, Any]:
    desde = await ingresos.verificable_desde(db)
    items = await _items(db) if desde else []
    return {"verificable_desde": desde, "resumen": ingresos.resumen(items)}


@router_ingresos.get("/por-tienda", dependencies=[_panel])
async def leer_por_tienda(db: AsyncSession = Depends(get_motored_db_or_503)) -> Dict[str, Any]:
    desde = await ingresos.verificable_desde(db)
    items = await _items(db) if desde else []
    return {"verificable_desde": desde, "tiendas": ingresos.por_tienda(items)}


@router_ingresos.get("/detalle", dependencies=[_panel])
async def leer_detalle(
    sucursal: Optional[uuid.UUID] = Query(None),
    estado: Optional[str] = Query(None),
    min_dias: Optional[int] = Query(None, ge=0),
    max_dias: Optional[int] = Query(None, ge=0),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> Dict[str, Any]:
    if estado is not None and estado not in (
            ingresos.SIN_CONFIRMAR, *ingresos.ESTADOS_CONFIRMABLES):
        raise HTTPException(status_code=422, detail=MSG_ESTADO_FILTRO)
    if min_dias is not None and max_dias is not None and min_dias > max_dias:
        raise HTTPException(status_code=422, detail=MSG_RANGO_DIAS)
    desde = await ingresos.verificable_desde(db)
    items = await _items(db, sucursal) if desde else []
    if estado is not None:
        items = [i for i in items if i["estado"] == estado]
    if min_dias is not None:
        items = [i for i in items if i["dias"] >= min_dias]
    if max_dias is not None:
        items = [i for i in items if i["dias"] <= max_dias]
    return {"verificable_desde": desde, "items": items}


@router_ingresos.get("/historial", dependencies=[_panel])
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


@router_ingresos.get("/asesor", dependencies=[_panel])
async def leer_de_asesor(
    sucursal: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> Dict[str, Any]:
    return await ingresos.para_asesor(db, [sucursal])


async def _actor_de(user: MotoredUser, db: AsyncSession) -> ingresos.Actor:
    usuario = (await db.execute(
        select(Usuario).where(Usuario.id == uuid.UUID(str(user.user_id)))
    )).scalars().first()
    if usuario is None:
        raise HTTPException(status_code=403, detail="No tiene permisos para realizar esta acción.")
    return ingresos.Actor(
        nombre=usuario.nombre, usuario_id=usuario.id,
        cedula=usuario.cedula if usuario.cedula_aprobada else None)


@router_ingresos.post("/confirmar", dependencies=[Depends(require_roles(*ROLES_CONFIRMA))])
async def confirmar(
    cuerpo: ConfirmarIn,
    user: MotoredUser = Depends(get_current_motored_user),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> Dict[str, Any]:
    actor = await _actor_de(user, db)
    try:
        return await ingresos.confirmar(
            db, cuerpo.factura, cuerpo.sucursal_id, cuerpo.estado, actor, "web")
    except ingresos.PendienteError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)


@router_ingresos.get("/plantilla", dependencies=[Depends(require_roles(*ROLES_PLANTILLA))])
async def descargar_plantilla(
    factura: str = Query(...), sucursal: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> Response:
    clave = ingresos.parsear_factura(factura)
    if clave is None:
        raise HTTPException(status_code=422, detail=ingresos.MSG_FACTURA)
    try:
        datos = await plantilla.preparar(db, clave, sucursal, hoy_bogota())
    except plantilla.PlantillaError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    return Response(
        content=plantilla.construir_libro(datos), media_type=plantilla.XLSX,
        headers={"Content-Disposition": (
            f'attachment; filename="Entrada_compra_{datos.prefijo_rh}'
            f'{datos.numero_rh}.xlsx"')})


# ---------------------------------------------------------------------------
# Transfers between stores
# ---------------------------------------------------------------------------

class ConfirmarTrasladoIn(BaseModel):
    documento: str
    bodega_salida: str
    estado: str


async def _traslados(
    db: AsyncSession, sucursal: Optional[uuid.UUID] = None,
) -> List[Dict[str, Any]]:
    return await traslados.pendientes(db, None if sucursal is None else [sucursal])


@router_traslados.get("", dependencies=[_panel])
async def leer_resumen_traslados(
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> Dict[str, Any]:
    return {"ultima_carga": await traslados.ultima_carga(db),
            "resumen": traslados.resumen(await _traslados(db))}


@router_traslados.get("/por-tienda", dependencies=[_panel])
async def leer_traslados_por_tienda(
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> Dict[str, Any]:
    return {"ultima_carga": await traslados.ultima_carga(db),
            "tiendas": traslados.por_tienda(await _traslados(db))}


@router_traslados.get("/detalle", dependencies=[_panel])
async def leer_detalle_traslados(
    sucursal: Optional[uuid.UUID] = Query(None),
    estado: Optional[str] = Query(None),
    min_dias: Optional[int] = Query(None, ge=0),
    max_dias: Optional[int] = Query(None, ge=0),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> Dict[str, Any]:
    if estado is not None and estado not in (
            traslados.SIN_CONFIRMAR, *traslados.ESTADOS_CONFIRMABLES):
        raise HTTPException(status_code=422, detail=MSG_ESTADO_FILTRO)
    if min_dias is not None and max_dias is not None and min_dias > max_dias:
        raise HTTPException(status_code=422, detail=MSG_RANGO_DIAS)
    items = await _traslados(db, sucursal)
    if estado is not None:
        items = [i for i in items if i["estado"] == estado]
    if min_dias is not None:
        items = [i for i in items if i["dias"] >= min_dias]
    if max_dias is not None:
        items = [i for i in items if i["dias"] <= max_dias]
    return {"ultima_carga": await traslados.ultima_carga(db), "items": items}


@router_traslados.get("/historial", dependencies=[_panel])
async def leer_historial_traslado(
    documento: str = Query(...), bodega_salida: str = Query(...),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> Dict[str, Any]:
    if not documento.strip() or not bodega_salida.strip():
        raise HTTPException(status_code=422, detail=traslados.MSG_TRASLADO)
    return {"historial": await traslados.historial(db, documento, bodega_salida)}


@router_traslados.get("/asesor", dependencies=[_panel])
async def leer_traslados_de_asesor(
    sucursal: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> Dict[str, Any]:
    return await traslados.para_asesor(db, [sucursal])


@router_traslados.post(
    "/confirmar", dependencies=[Depends(require_roles(*ROLES_CONFIRMA))])
async def confirmar_traslado(
    cuerpo: ConfirmarTrasladoIn,
    user: MotoredUser = Depends(get_current_motored_user),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> Dict[str, Any]:
    actor = await _actor_de(user, db)
    try:
        return await traslados.confirmar(
            db, cuerpo.documento, cuerpo.bodega_salida, cuerpo.estado, actor,
            "web")
    except traslados.PendienteError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)


router = APIRouter(
    prefix="/gestion-repuestos",
    dependencies=[Depends(require_motored_ready)],
)
router.include_router(router_ingresos)
router.include_router(router_traslados)
