"""
Motored Pedidos — dependencias de FastAPI (sdd/motored-pedidos-cimientos,
Fase 2 + Fase 3 wiring, ADR-2 y ADR-4).

`get_current_motored_user` es DELIBERADAMENTE distinto de
`app.api.deps.get_current_user` (que es solo-claims, sin ir a la base de
datos): ADR-2 exige que el scoping por SUCURSAL y la desactivación de un
usuario puedan revocarse de inmediato, no recién cuando expire un token de
8 horas.

Fase 2 resolvía el usuario a través de un seam inyectable
(`_unwired_user_lookup`, fail-closed con 503) porque la tabla `usuario`
todavía no existía. Ahora que el modelo `Usuario` existe (Fase 3, task 3.1),
`get_motored_user_lookup` está conectado a la consulta ORM real
(`app.motored.services.auth.crear_lookup_real`) -- el seam sigue siendo
swappable vía `app.dependency_overrides` (así es como los tests de
aislamiento de la Fase 2, `tests/motored/test_auth_isolation.py`, siguen
funcionando sin cambios), pero la implementación por defecto ya no es una
falsa. `get_motored_user_lookup` ahora depende de `get_motored_db_or_503`
(la misma composición de dependencia-sobre-dependencia que
`app.api.deps.get_current_user` usaría si necesitara ir a la base de datos)
porque debe poder consultarla.
"""
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.motored.auth import decode_motored_token, motored_secret_is_safe
from app.motored.database import get_motored_db
from app.motored.services.auth import MotoredUser, MotoredUserLookup, crear_lookup_real
from app.motored.services.trabajos import supervisor

MOTORED_UNAVAILABLE_DETAIL = {"code": "MOTORED_UNAVAILABLE"}
MOTORED_DB_UNAVAILABLE_DETAIL = {"code": "MOTORED_DB_UNAVAILABLE"}


async def get_motored_db_or_503(
    db: AsyncSession = Depends(get_motored_db),
) -> AsyncSession:
    """Envoltorio delgado sobre `get_motored_db`: hace una sonda de
    conectividad trivial (`SELECT 1`) para que una base de datos de
    Motored inalcanzable se traduzca en un 503 MOTORED_DB_UNAVAILABLE
    limpio, en vez de un error de conexión sin manejar / 500. No toca en
    absoluto el engine/sesión de asc360 (aislamiento de outage, ADR-4)."""
    try:
        await db.execute(text("SELECT 1"))
    except (OSError, DBAPIError, OperationalError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=MOTORED_DB_UNAVAILABLE_DETAIL,
        ) from exc
    return db


def get_motored_user_lookup(
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> MotoredUserLookup:
    """Dependencia-seam: por defecto retorna la consulta ORM REAL contra
    `usuario` (Fase 3), ligada a la sesión de esta request. Sigue siendo
    swappable vía `app.dependency_overrides` -- exactamente lo que
    `tests/motored/test_auth_isolation.py` (Fase 2) sigue usando, sin
    ningún cambio de su lado."""
    return crear_lookup_real(db)


async def get_current_motored_user(
    authorization: Optional[str] = Header(None),
    lookup: MotoredUserLookup = Depends(get_motored_user_lookup),
) -> MotoredUser:
    """Decodifica el token de Motored y resuelve el usuario vía el seam
    inyectable. Rechaza igual que `app.api.deps.get_current_user`: 401
    genérico, sin filtrar cuál fue el problema exacto."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No autenticado. Token de acceso de Motored requerido.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not authorization or not authorization.startswith("Bearer "):
        raise credentials_exception

    token = authorization.split(" ", 1)[1]
    payload = decode_motored_token(token)
    if not payload:
        raise credentials_exception

    user_id = payload.get("sub")
    role = payload.get("role")
    if not user_id or not role:
        raise credentials_exception

    user = await lookup(user_id)
    if not user or not user.activo:
        raise credentials_exception

    return user


def require_roles(*roles: str):
    """Fábrica de dependencia: exige que el usuario autenticado tenga uno
    de los roles dados. Rechazo server-side siempre -- nunca confía en que
    la UI oculte la acción."""

    async def _check_role(user: MotoredUser = Depends(get_current_motored_user)) -> MotoredUser:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene permisos para realizar esta acción.",
            )
        return user

    return _check_role


async def require_motored_ready() -> None:
    """Dependencia de disponibilidad (ADR-4): 503 MOTORED_UNAVAILABLE si el
    módulo está apagado (`MOTORED_ENABLED=false`) o si el guard fail-closed
    de secreto (ADR-1) no se cumple. Se usa en cada endpoint de Motored
    antes de tocar la base de datos.

    También es el seam de arranque perezoso del supervisor de Fase 2
    "Ingesta" (sdd/motored-pedidos-ingesta, ADR-1): `ensure_started()` es
    un chequeo O(1) después de la primera llamada, por eso `app/main.py`
    no necesita ningún hook `lifespan` y queda byte-a-byte sin tocar."""
    if not settings.MOTORED_ENABLED or not motored_secret_is_safe():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=MOTORED_UNAVAILABLE_DETAIL,
        )
    supervisor.ensure_started()
