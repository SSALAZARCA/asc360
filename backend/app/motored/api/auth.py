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
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.limiter import limiter
from app.core.security import verify_password
from app.motored.auth import create_motored_token
from app.motored.deps import get_motored_db_or_503, require_motored_ready
from app.motored.models.usuario import Usuario

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


@router.post("/login", response_model=MotoredLoginResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,
    payload: MotoredLoginRequest,
    db: AsyncSession = Depends(get_motored_db_or_503),
):
    """Login de Motored. Nunca revela si el problema fue el email o la
    contraseña (spec 'Invalid credentials are rejected generically') --
    email inexistente, usuario inactivo y contraseña incorrecta comparten
    EXACTAMENTE el mismo 401."""
    generic_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=_GENERIC_DETAIL,
        headers={"WWW-Authenticate": "Bearer"},
    )

    result = await db.execute(select(Usuario).where(Usuario.email == payload.email))
    usuario = result.scalars().first()

    if not usuario or not usuario.activo:
        raise generic_error

    if not verify_password(payload.password, usuario.hashed_password):
        raise generic_error

    role_value = usuario.role.value if hasattr(usuario.role, "value") else usuario.role
    token = create_motored_token(sub=str(usuario.id), role=role_value)

    return MotoredLoginResponse(
        access_token=token,
        user={
            "id": str(usuario.id),
            "nombre": usuario.nombre,
            "email": usuario.email,
            "role": role_value,
        },
    )
