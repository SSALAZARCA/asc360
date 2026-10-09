"""
Motored -- inventory counts, public pair access (odd/motored-conteos-
inventario, WU7/WU8; design §6.2, §5.3, §7, §8.1-§8.3, §8.6).

Prefix `/api/motored/publico/conteos` (WU7 access, WU8 readings).
PUBLIC: no `get_current_motored_user` (pairs have no user account), so
the role/path confinement does not apply;
each route authenticates by itself:

- `POST /{slug}/unirse`: the 6-digit code plus 2-3 members. slowapi
  `10/minute` per IP on top of the DB counters in `services/conteos/
  sesiones.py`. Any failure is the same 401 "Código o enlace no válidos.";
  a locked client gets 429.
- every other route: `Authorization: Bearer <device token>` through
  `sesion_de_pareja` (a CONECTADA session of a running conteo, on this
  slug); anything else is 401 SESION_INACTIVA.

Readings (WU8, `services/conteos/lecturas.py`): the referencia catalogue
(ETag / 304, gzip), the store's locations, setting the current location
(a scanned `UBI-…` label or a typed code; an unknown code is created as
'PAREJA'), idempotent batches of up to 100 readings, voiding one's own
reading and the recent readings with a per-location summary.

Every response, errors included, is `no-store` and `noindex`
(`RutaPublica`). The join body is read by hand so a validation error never
echoes a cédula back. No response carries a cédula, an expected quantity,
a cost or a difference (the count is blind).
"""
from datetime import datetime, timezone
import uuid
from typing import Any, Callable, Optional

from fastapi import (
    APIRouter, Depends, Header, HTTPException, Query, Request,
)
from fastapi import Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.limiter import limiter
from app.motored.api.conteos import error_http
from app.motored.deps import get_motored_db_or_503, require_motored_ready
from app.motored.schemas import conteos as esquemas
from app.motored.services.conteos import (
    catalogo, errores, lecturas, sesiones, ubicaciones,
)

UNIRSE_LIMITE = "10/minute"
RECIENTES_POR_DEFECTO = 50
RECIENTES_MAXIMO = 200
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


# --- readings (WU8) ----------------------------------------------------------


def _ubicacion_pareja(ubicacion) -> esquemas.UbicacionPareja:
    return esquemas.UbicacionPareja(
        id=ubicacion.id, codigo=ubicacion.codigo, nombre=ubicacion.nombre)


def _acepta_gzip(request: Request) -> bool:
    return "gzip" in request.headers.get("accept-encoding", "").lower()


@router.get("/{slug}/catalogo", response_model=esquemas.CatalogoSalida)
async def ver_catalogo(
    request: Request,
    pareja: sesiones.Pareja = Depends(sesion_de_pareja),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> Response:
    """`{version, referencias: [[code, name], ...]}` of ALL referencias.
    `If-None-Match` with the current ETag answers 304 with no body."""
    actual = await catalogo.obtener(db)
    cabeceras = {"ETag": actual.etag, "Vary": "Accept-Encoding"}
    if catalogo.coincide(actual.etag, request.headers.get("if-none-match")):
        return Response(status_code=304, headers=cabeceras)
    if _acepta_gzip(request):
        cabeceras["Content-Encoding"] = "gzip"
        return Response(
            actual.comprimido, media_type="application/json",
            headers=cabeceras)
    return Response(
        actual.cuerpo, media_type="application/json", headers=cabeceras)


@router.get(
    "/{slug}/ubicaciones", response_model=list[esquemas.UbicacionPareja])
async def ver_ubicaciones(
    pareja: sesiones.Pareja = Depends(sesion_de_pareja),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> Any:
    """The store's active locations (code and name)."""
    filas = await ubicaciones.listar(
        db, pareja.conteo.sucursal_id, solo_activas=True)
    return [_ubicacion_pareja(u) for u in filas]


@router.put("/{slug}/ubicacion", response_model=esquemas.UbicacionFijada)
async def fijar_ubicacion(
    cuerpo: esquemas.UbicacionFijar,
    pareja: sesiones.Pareja = Depends(sesion_de_pareja),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> Any:
    """Body `{codigo, nombre?}`: sets the current location, creating it
    ('PAREJA') when the store does not have that code."""
    try:
        fijada = await ubicaciones.fijar(
            db, pareja.sesion, pareja.conteo.sucursal_id, cuerpo.codigo,
            cuerpo.nombre)
    except errores.ErrorConteo as error:
        raise error_http(error) from error
    await db.commit()
    return esquemas.UbicacionFijada(
        ubicacion=_ubicacion_pareja(fijada.ubicacion),
        creada=fijada.creada)


@router.post("/{slug}/lecturas", response_model=esquemas.LecturasSalida)
async def registrar_lecturas(
    cuerpo: esquemas.LecturasEntrada,
    pareja: sesiones.Pareja = Depends(sesion_de_pareja),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> Any:
    """A batch of up to 100 readings, idempotent by the client `id`."""
    items = [lecturas.Entrada(
        id=i.id, codigo_leido=i.codigo_leido, cantidad=i.cantidad,
        leida_en=i.leida_en, metodo=i.metodo,
        forzar_desconocido=i.forzar_desconocido) for i in cuerpo.lecturas]
    try:
        resultado = await lecturas.registrar(
            db, pareja.sesion, pareja.conteo, items)
    except errores.ErrorConteo as error:
        raise error_http(error) from error
    await db.commit()
    return esquemas.LecturasSalida(
        aceptadas=resultado.aceptadas, duplicadas=resultado.duplicadas,
        desconocidos=[
            esquemas.CodigoDesconocido(id=i, codigo=c)
            for i, c in resultado.desconocidos],
        rechazadas=[
            esquemas.LecturaRechazada(id=i, motivo=m)
            for i, m in resultado.rechazadas],
        referencias=resultado.referencias)


@router.post(
    "/{slug}/lecturas/{lectura_id}/anular",
    response_model=esquemas.AnulacionSalida)
async def anular_lectura(
    lectura_id: uuid.UUID,
    pareja: sesiones.Pareja = Depends(sesion_de_pareja),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> Any:
    """Voids one of this device's readings while its round is open."""
    try:
        lectura = await lecturas.anular(
            db, pareja.sesion, pareja.conteo, lectura_id, _ahora())
    except errores.ErrorConteo as error:
        raise error_http(error) from error
    await db.commit()
    return esquemas.AnulacionSalida(
        id=lectura.id, anulada_en=lectura.anulada_en)


def _lectura_pareja(fila) -> esquemas.LecturaPareja:
    return esquemas.LecturaPareja(
        id=fila[0], codigo=fila[1], descripcion=fila[2], cantidad=fila[3],
        metodo=fila[4],
        ubicacion=esquemas.UbicacionCorta(codigo=fila[5], nombre=fila[6]),
        leida_en=fila[7], anulada_en=fila[8])


@router.get(
    "/{slug}/lecturas/recientes", response_model=esquemas.RecientesSalida)
async def lecturas_recientes(
    limite: int = Query(
        default=RECIENTES_POR_DEFECTO, ge=1, le=RECIENTES_MAXIMO),
    pareja: sesiones.Pareja = Depends(sesion_de_pareja),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> Any:
    """This device's last readings (voided ones flagged) and what it
    counted per code in its current location."""
    vista = await lecturas.recientes(db, pareja.sesion, limite)
    ubicacion = vista.ubicacion
    return esquemas.RecientesSalida(
        ubicacion_actual=(
            None if ubicacion is None else _ubicacion_pareja(ubicacion)),
        lecturas=[_lectura_pareja(f) for f in vista.lecturas],
        resumen_ubicacion=[
            esquemas.ResumenUbicacion(
                codigo=f[0], descripcion=f[1], cantidad=f[2],
                lecturas=f[3])
            for f in vista.resumen])
