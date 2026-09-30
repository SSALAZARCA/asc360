"""
Motored Pedidos — router de autenticación (sdd/motored-pedidos-cimientos,
Fase 4, ADR-1).

Mirrors `app/api/v1/auth.py`'s password-verification mechanism EXACTLY
(`app.core.security.verify_password`/`get_password_hash`, plain bcrypt) --
this is the one thing ADR-1 explicitly says to reuse from asc360. What it
does NOT reuse is `create_access_token`/`decode_access_token`: this router
issues a `create_motored_token` (own secret, own `iss`/`aud`), never an
asc360-scoped token.

Gated by `require_motored_ready` (503 if the module is off/misconfigured),
never by `get_current_motored_user` -- this IS the login endpoint, there is
no user yet to authenticate.
"""
import uuid
from functools import lru_cache
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.limiter import limiter
from app.core.security import get_password_hash, verify_password
from app.motored.auth import create_motored_token
from app.motored.deps import MotoredUser, get_current_motored_user, get_motored_db_or_503, require_motored_ready
from app.motored.models.usuario import Usuario
from app.motored.services import auditoria, login_bloqueo, login_eventos
from app.motored.services.password_policy import aplicar_password, validar_password

router = APIRouter(
    prefix="/auth",
    tags=["motored-auth"],
    dependencies=[Depends(require_motored_ready)],
)


class MotoredLoginRequest(BaseModel):
    email: EmailStr
    password: str


class MotoredLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


_GENERIC_DETAIL = "Credenciales incorrectas"
_MOTIVO_CREDENCIALES = "CREDENCIALES"


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return get_password_hash("dummy-password-for-timing")


def _generic_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=_GENERIC_DETAIL,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _locked_error() -> HTTPException:
    return HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=login_bloqueo.LOCKED_DETAIL)


def _motivo_rechazo(usuario: Optional[Usuario]) -> Optional[str]:
    """Why this account cannot even try a password (internal, logged only);
    None when it can. `status or "approved"` mirrors
    `services/auth.py::obtener_usuario_motored`: hand-built rows without
    `status=` have None at the Python level. `ASESOR_MOSTRADOR` rows have no
    `hashed_password` and never get web credentials."""
    if usuario is None or not usuario.hashed_password:
        return _MOTIVO_CREDENCIALES
    if not usuario.activo:
        return "INACTIVO"
    if (usuario.status or "approved") != "approved":
        return "PENDIENTE"
    return None


async def _cerrar_intento(db, request, email, usuario, resultado, motivo) -> None:
    await login_eventos.registrar(db, request, email, usuario.id if usuario else None, resultado, motivo)
    await db.commit()


async def _rechazar(db, request, email, usuario, motivo, now):
    """Count the failure (DB for existing accounts, memory for unknown emails),
    log it and answer: 429 if that failure locked the account, else the
    generic 401. The caller never learns which `motivo` applied."""
    if usuario is None:
        locked_until = login_bloqueo.registrar_fallo_desconocido(email)
    else:
        locked_until = await login_bloqueo.registrar_fallo(db, usuario.id, now)
    await _cerrar_intento(db, request, email, usuario, "FALLO", motivo)
    raise _locked_error() if locked_until else _generic_error()


def _esta_bloqueado(usuario: Optional[Usuario], email: str, now) -> bool:
    if usuario is None:
        return login_bloqueo.bloqueado_desconocido(email, now) is not None
    return login_bloqueo.bloqueado_hasta_vigente(usuario, now) is not None


@router.post("/login", response_model=MotoredLoginResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,
    payload: MotoredLoginRequest,
    db: AsyncSession = Depends(get_motored_db_or_503),
):
    """Login de Motored. Nunca revela si el problema fue el email o la
    contraseña (spec 'Invalid credentials are rejected generically') --
    email inexistente, usuario inactivo/pendiente y contraseña incorrecta
    comparten EXACTAMENTE el mismo 401, y tras 5 fallos seguidos (existente o
    no) el mismo 429 de bloqueo (T9). Cada intento queda en `login_evento`
    (T10). Un bcrypt de relleno evita que "no existe" responda mucho más
    rápido que "contraseña incorrecta"; los caminos bloqueados no hacen
    bcrypt en ningún caso, así que tampoco se distinguen entre sí."""
    email = login_bloqueo.normalizar_email(payload.email)
    now = login_bloqueo.ahora()
    result = await db.execute(select(Usuario).where(Usuario.email == payload.email))
    usuario = result.scalars().first()

    if _esta_bloqueado(usuario, email, now):
        await _cerrar_intento(db, request, email, usuario, "BLOQUEADO", "CUENTA_BLOQUEADA")
        raise _locked_error()

    motivo = _motivo_rechazo(usuario)
    if motivo is None:
        if verify_password(payload.password, usuario.hashed_password):
            return await _aceptar(db, request, email, usuario)
        motivo = _MOTIVO_CREDENCIALES
    else:
        verify_password(payload.password, _dummy_hash())
    await _rechazar(db, request, email, usuario, motivo, now)


async def _aceptar(db, request, email, usuario) -> MotoredLoginResponse:
    if usuario.login_fallidos or usuario.login_ventana_inicio or usuario.bloqueado_hasta:
        login_bloqueo.limpiar_bloqueo(usuario)
    await _cerrar_intento(db, request, email, usuario, "EXITO", None)
    return _session_response(usuario)


def _session_response(usuario: Usuario) -> MotoredLoginResponse:
    role_value = usuario.role.value if hasattr(usuario.role, "value") else usuario.role
    return MotoredLoginResponse(
        access_token=create_motored_token(sub=str(usuario.id), role=role_value),
        user={
            "id": str(usuario.id),
            "nombre": usuario.nombre,
            "email": usuario.email,
            "role": role_value,
            "must_change_password": bool(usuario.must_change_password),
        },
    )


class MotoredChangePasswordRequest(BaseModel):
    """Plain strings on purpose: pydantic's automatic 422 echoes the received
    value, and a password must never travel back in a response."""

    actual: str
    nueva: str


@router.post("/password", response_model=MotoredLoginResponse)
@limiter.limit("5/minute")
async def change_own_password(
    request: Request,
    payload: MotoredChangePasswordRequest,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(get_current_motored_user),
):
    """Any authenticated web user changes their own password. Every other
    session is cut (`password_changed_at`); the response carries a fresh
    token so this tab stays logged in."""
    result = await db.execute(select(Usuario).where(Usuario.id == uuid.UUID(user.user_id)))
    usuario = result.scalars().first()
    if not usuario or not usuario.hashed_password or not verify_password(payload.actual, usuario.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La contraseña actual no es correcta.")
    validar_password(payload.nueva, usuario.email)
    if payload.nueva == payload.actual:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La nueva contraseña debe ser distinta de la actual.",
        )
    aplicar_password(usuario, payload.nueva)
    auditoria.audit_password_reset(db, "usuario", usuario.id, usuario.id)
    await db.commit()
    return _session_response(usuario)
