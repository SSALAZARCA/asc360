"""
Motored -- the asesor's public report (odd/motored-reporte-diario-asesor, T3b).

`POST /publico/informe/{token}` with `{"cedula"}`. PUBLIC: it has no
`get_current_motored_user`, so none of the role/path confinement applies
(that lives in that dependency, not in the router). Abuse is bounded by the
per-link lock in `services/informe_publico`.

Every response, success or error (503 included), carries `Cache-Control:
no-store` and `X-Robots-Tag: noindex, nofollow`: `_RutaPublica` wraps the
handler so it holds for errors raised by dependencies too. The body is read
by hand, so a malformed one is just a wrong cédula, never a 422.

`POST /{token}/traslados` and `POST /{token}/traslados/confirmar` give the
asesor the transfers her store must receive and let her confirm them
(odd/tasks/motored-traslados-pendientes.md, T2).
"""
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.deps import get_motored_db_or_503, require_motored_ready
from app.motored.services import informe_publico as servicio

_CABECERAS = {
    "Cache-Control": "no-store",
    "X-Robots-Tag": "noindex, nofollow",
}


class _RutaPublica(APIRoute):
    def get_route_handler(self) -> Callable:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                respuesta = await original(request)
            except HTTPException as exc:
                respuesta = JSONResponse(
                    {"detail": exc.detail}, status_code=exc.status_code,
                    headers=exc.headers)
            respuesta.headers.update(_CABECERAS)
            return respuesta

        return handler


router = APIRouter(
    prefix="/publico/informe",
    tags=["motored-informe-publico"],
    dependencies=[Depends(require_motored_ready)],
    route_class=_RutaPublica,
)


@router.post("/{token}")
async def abrir_informe(
    token: str, request: Request,
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> Any:
    try:
        cuerpo = await request.json()
    except ValueError:
        cuerpo = None
    cedula = cuerpo.get("cedula") if isinstance(cuerpo, dict) else None
    try:
        return await servicio.abrir_informe(db, token, cedula)
    except servicio.InformeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.post("/{token}/pendientes")
async def confirmar_pendiente(
    token: str, request: Request,
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> Any:
    """The asesor confirms "Llegó" / "No ha llegado" for an invoice of her
    store: `{cedula, factura, estado}`, same token + cédula + lock as the
    report. Answers the updated item."""
    try:
        cuerpo = await request.json()
    except ValueError:
        cuerpo = None
    if not isinstance(cuerpo, dict):
        cuerpo = {}
    try:
        return await servicio.confirmar_pendiente(
            db, token, cuerpo.get("cedula"), cuerpo.get("factura"),
            cuerpo.get("estado"))
    except servicio.InformeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)


async def _cuerpo(request: Request) -> dict:
    try:
        cuerpo = await request.json()
    except ValueError:
        return {}
    return cuerpo if isinstance(cuerpo, dict) else {}


@router.post("/{token}/traslados")
async def listar_traslados(
    token: str, request: Request,
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> Any:
    """The transfers her store(s) must receive: `{cedula}`, same token +
    cédula + lock as the report. Answers `{ultima_carga, items, resumen}`."""
    cuerpo = await _cuerpo(request)
    try:
        return await servicio.traslados_del_asesor(
            db, token, cuerpo.get("cedula"))
    except servicio.InformeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.post("/{token}/traslados/confirmar")
async def confirmar_traslado(
    token: str, request: Request,
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> Any:
    """The asesor confirms "Recibido" / "No ha llegado" for a transfer her
    store receives: `{cedula, documento, bodega_salida, estado}`. Answers the
    updated item."""
    cuerpo = await _cuerpo(request)
    try:
        return await servicio.confirmar_traslado(
            db, token, cuerpo.get("cedula"), cuerpo.get("documento"),
            cuerpo.get("bodega_salida"), cuerpo.get("estado"))
    except servicio.InformeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
