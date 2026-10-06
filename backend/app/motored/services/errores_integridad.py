"""
Motored -- readable Spanish messages for a database `IntegrityError`.

The maestros upload and CRUD check every rule before writing, so an
IntegrityError at flush or COMMIT is either a race with another save on a
natural key, or a bug (a write in the wrong order, a missed rule). Every
handler used to answer "Otra carga modificó estos registros" for both, so
a bug looked like a race and retrying never helped.

`describir` reads the violated constraint and its SQLSTATE from the
driver (asyncpg keeps its error as `__cause__` of `exc.orig`; psycopg
exposes `diag`), falls back to the message text, and logs both.
`respuesta` maps the violation to an HTTP error: a known constraint gets
its own message, any other unique violation is a race (409), and anything
else is an internal error naming the constraint (500).
"""
import logging
import re
from typing import Any, Iterable, NamedTuple, Optional

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

VIOLACION_UNICA = "23505"
VIOLACION_LLAVE_FORANEA = "23503"

MENSAJE_CARRERA = (
    "Otra carga modificó estos registros en este momento. Espere unos "
    "segundos y vuelva a subir el archivo."
)

# Constraints a person can understand, by their Postgres name.
MENSAJES_CONOCIDOS = {
    "sucursal_nombre_key": "Dos sucursales quedarían con el mismo nombre.",
    "uq_sucursal_codigo_co": "El Código C.O. ya es de otra sucursal.",
    "bodega_codigo_key": "La bodega ya existe.",
}

_RESTRICCION_EN_TEXTO = re.compile(r'constraint "([^"]+)"')


class Violacion(NamedTuple):
    """SQLSTATE and constraint name; None when the driver did not say."""

    sqlstate: Optional[str]
    restriccion: Optional[str]


def _fuentes(exc: IntegrityError) -> Iterable[Any]:
    orig = getattr(exc, "orig", None)
    for fuente in (orig, getattr(orig, "__cause__", None)):
        if fuente is not None:
            yield fuente


def _atributo(exc: IntegrityError, nombre: str) -> Optional[str]:
    """`nombre` from the error itself or its `diag`, first found."""
    for fuente in _fuentes(exc):
        for origen in (fuente, getattr(fuente, "diag", None)):
            valor = getattr(origen, nombre, None)
            if isinstance(valor, str) and valor:
                return valor
    return None


def _sqlstate_del_texto(texto: str) -> Optional[str]:
    texto = texto.lower()
    if "duplicate key" in texto or "unique constraint" in texto:
        return VIOLACION_UNICA
    if "foreign key" in texto:
        return VIOLACION_LLAVE_FORANEA
    return None


def describir(exc: IntegrityError, origen: str) -> Violacion:
    """The violation behind `exc`, logged with `origen` (who caught it)."""
    texto = str(getattr(exc, "orig", None) or "")
    coincidencia = _RESTRICCION_EN_TEXTO.search(texto)
    violacion = Violacion(
        _atributo(exc, "sqlstate") or _atributo(exc, "pgcode")
        or _sqlstate_del_texto(texto),
        _atributo(exc, "constraint_name")
        or (coincidencia.group(1) if coincidencia else None),
    )
    logger.warning(
        "%s: IntegrityError en la restricción %s (SQLSTATE %s): %s",
        origen, violacion.restriccion or "desconocida",
        violacion.sqlstate or "desconocido", texto,
    )
    return violacion


def mensaje_interno(violacion: Violacion) -> str:
    return (
        "No se pudo guardar por un error interno (restricción "
        f"{violacion.restriccion or 'desconocida'}). Avise a soporte; "
        "reintentar no lo soluciona."
    )


def respuesta(
    violacion: Violacion, mensaje_carrera: str = MENSAJE_CARRERA,
) -> HTTPException:
    """409 with the constraint's own message or, for any other unique
    violation, `mensaje_carrera`; 500 naming the constraint otherwise."""
    conocido = MENSAJES_CONOCIDOS.get(violacion.restriccion or "")
    if conocido:
        return HTTPException(status.HTTP_409_CONFLICT, detail=conocido)
    if violacion.sqlstate == VIOLACION_UNICA:
        return HTTPException(
            status.HTTP_409_CONFLICT, detail=mensaje_carrera
        )
    return HTTPException(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=mensaje_interno(violacion),
    )
