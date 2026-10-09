"""
Motored -- inventory counts, public pair access (odd/motored-conteos-
inventario, WU7; design §6.2, §5.3, §8.1-§8.3, §8.6).

Prefix `/api/motored/publico/conteos`. PUBLIC: no `get_current_motored_user`
(pairs have no user account), so the role/path confinement does not apply;
each route authenticates by itself:

- `POST /{slug}/unirse`: the 6-digit code plus 2-3 members. slowapi
  `10/minute` per IP on top of the DB counters in `services/conteos/
  sesiones.py`. Any failure is the same 401 "Código o enlace no válidos.";
  a locked client gets 429.
- every other route: `Authorization: Bearer <device token>` through
  `sesion_de_pareja` (a CONECTADA session of a running conteo, on this
  slug); anything else is 401 SESION_INACTIVA.

Every response, errors included, is `no-store` and `noindex`
(`RutaPublica`). The join body is read by hand so a validation error never
echoes a cédula back. No response carries a cédula, an expected quantity,
a cost or a difference (the count is blind).
"""
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi import Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.limiter import limiter
from app.motored.api.conteos import error_http
from app.motored.deps import get_motored_db_or_503, require_motored_ready
from app.motored.schemas import conteos as esquemas
from app.motored.services.conteos import errores, sesiones

UNIRSE_LIMITE = "10/minute"
_CABECERAS = {
    "Cache-Control": "no-store",
    "X-Robots-Tag": "noindex, nofollow",
}


class RutaPublica(APIRoute):
    """Adds the no-store / noindex headers to every answer, including the
    errors raised by dependencies."""

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
    prefix="/publico/conteos",
    tags=["motored-conteos-publico"],
    dependencies=[Depends(require_motored_ready)],
    route_class=RutaPublica,
)


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _token(authorization: Optional[str]) -> Optional[str]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return authorization.split(" ", 1)[1].strip() or None


async def sesion_de_pareja(
    slug: str,
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> sesiones.Pareja:
    """The device's active session; 401 SESION_INACTIVA otherwise."""
    try:
        pareja = await sesiones.pareja_activa(db, slug, _token(authorization))
    except errores.ErrorConteo as error:
        raise error_http(error) from error
    if sesiones.tocar_actividad(pareja.sesion, _ahora()):
        await db.commit()
    return pareja


async def _entrada(request: Request) -> esquemas.UnirseEntrada:
    try:
        cuerpo = await request.json()
    except ValueError:
        cuerpo = None
    try:
        return esquemas.UnirseEntrada.model_validate(cuerpo)
    except ValidationError:
        raise error_http(errores.DatosIngresoInvalidos()) from None


def _cliente(request: Request) -> str:
    return request.client.host if request.client else "desconocido"


@router.post(
    "/{slug}/unirse", response_model=esquemas.UnirseSalida,
    status_code=201)
@limiter.limit(UNIRSE_LIMITE)
async def unirse(
    slug: str, request: Request,
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> Any:
    """Body: `{codigo, dispositivo, integrantes: [{nombre, cedula}]}`."""
    entrada = await _entrada(request)
    integrantes = [(i.nombre, i.cedula) for i in entrada.integrantes]
    try:
        ingreso = await sesiones.unirse(
            db, slug, entrada.codigo, integrantes, entrada.dispositivo,
            _cliente(request))
    except errores.ErrorConteo as error:
        raise error_http(error) from error
    await db.commit()
    fila = ingreso.fila
    nombres = [p.nombre for p in fila.integrantes]
    return esquemas.UnirseSalida(
        sesion_token=ingreso.token, sesion_id=fila.sesion.id,
        etiqueta=sesiones.etiqueta(fila.numero, nombres),
        integrantes=nombres, sucursal=ingreso.sucursal,
        estado_conteo=ingreso.estado_conteo)


@router.get("/{slug}/sesion", response_model=esquemas.SesionPareja)
async def quien_soy(
    pareja: sesiones.Pareja = Depends(sesion_de_pareja),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> Any:
    """Pair label, member names and current location. Nothing else."""
    fila = await sesiones.describir(db, pareja.sesion)
    nombres = [p.nombre for p in fila.integrantes]
    ubicacion = fila.ubicacion
    return esquemas.SesionPareja(
        sesion_id=pareja.sesion.id,
        etiqueta=sesiones.etiqueta(fila.numero, nombres),
        integrantes=nombres, sucursal=pareja.sucursal,
        estado_conteo=pareja.conteo.estado,
        ubicacion_actual=(None if ubicacion is None else
                          esquemas.UbicacionSalida(
                              id=ubicacion.id, nombre=ubicacion.nombre)))


@router.post("/{slug}/salir", status_code=204, response_class=Response)
async def salir(
    pareja: sesiones.Pareja = Depends(sesion_de_pareja),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> Response:
    """The device leaves (DESCONECTADA); its readings are kept."""
    sesiones.salir(pareja.sesion, _ahora())
    await db.commit()
    return Response(status_code=204)
