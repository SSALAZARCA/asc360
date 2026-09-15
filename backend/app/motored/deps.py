"""
Motored Pedidos — dependencias de FastAPI (sdd/motored-pedidos-cimientos,
Fase 2, ADR-2 y ADR-4).

`get_current_motored_user` es DELIBERADAMENTE distinto de
`app.api.deps.get_current_user` (que es solo-claims, sin ir a la base de
datos): ADR-2 exige que el scoping por SUCURSAL y la desactivación de un
usuario puedan revocarse de inmediato, no recién cuando expire un token de
8 horas. Como el modelo `usuario` de Motored todavía no existe (Fase 3),
esta dependencia resuelve el usuario a través de un seam inyectable y
reemplazable (`get_motored_user_lookup`) -- Fase 3 conecta ahí la consulta
ORM real sin que este slice necesite la tabla `usuario`.
"""
from dataclasses import dataclass, field
from typing import Awaitable, Callable, List, Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.motored.auth import decode_motored_token, motored_secret_is_safe
from app.motored.database import get_motored_db

MOTORED_UNAVAILABLE_DETAIL = {"code": "MOTORED_UNAVAILABLE"}
MOTORED_DB_UNAVAILABLE_DETAIL = {"code": "MOTORED_DB_UNAVAILABLE"}


@dataclass
class MotoredUser:
    """Resultado de `get_current_motored_user`. Independiente del futuro
    modelo ORM `usuario` (Fase 3) -- solo lleva lo que las dependencias de
    autorización de este slice necesitan."""

    user_id: str
    role: str
    sucursal_ids: List[str] = field(default_factory=list)
    activo: bool = True


MotoredUserLookup = Callable[[str], Awaitable[Optional[MotoredUser]]]


async def _unwired_user_lookup(user_id: str) -> Optional[MotoredUser]:
    """Implementación por defecto del seam: intencionalmente NO hace
    ninguna consulta real todavía (no hay tabla `usuario` en la Fase 2).
    Fase 3 reemplaza esto -- vía `app.dependency_overrides` en producción
    (wiring real en `app/motored/api/*`) o en tests -- con la consulta ORM
    real contra `usuario`. Falla cerrado: cualquier request que llegue
    hasta acá sin que Fase 3/tests hayan provisto un lookup real es
    rechazada, nunca autenticada por accidente."""
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=MOTORED_UNAVAILABLE_DETAIL,
    )


def get_motored_user_lookup() -> MotoredUserLookup:
    """Dependencia-seam: swappable vía `app.dependency_overrides` hoy
    (tests de esta fase) y reemplazada por la consulta real a `usuario`
    en la Fase 4 (routers)."""
    return _unwired_user_lookup


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
    antes de tocar la base de datos."""
    if not settings.MOTORED_ENABLED or not motored_secret_is_safe():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=MOTORED_UNAVAILABLE_DETAIL,
        )


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
