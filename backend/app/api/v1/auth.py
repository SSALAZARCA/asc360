from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, EmailStr
from typing import Optional
from app.database import get_db
from app.models.user import User, UserStatus, Role
from app.core.security import verify_password, create_access_token, get_password_hash
from app.config import settings

router = APIRouter()


# ─── Schemas ─────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict

class TelegramAuthRequest(BaseModel):
    """Payload que Sonia envía cuando un usuario de Telegram interactúa con ella."""
    telegram_id: str
    name: Optional[str] = None
    phone: Optional[str] = None

class TelegramLinkRequest(BaseModel):
    """Para vincular manualmente un telegram_id a un usuario web existente."""
    user_id: str
    telegram_id: str


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _build_token_and_user(user: User) -> dict:
    """Genera el JWT y el dict de respuesta estandarizado para un usuario."""
    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "role": user.role.value,
            "tenant_id": str(user.tenant_id) if user.tenant_id else None,
            "telegram_id": user.telegram_id,
        }
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "name": user.name,
            "email": user.email,
            "role": user.role.value,
            "tenant_id": str(user.tenant_id) if user.tenant_id else None,
            "telegram_id": user.telegram_id,
        }
    }


# ─── Endpoint 1: Login Web (Email + Contraseña) ───────────────────────────────

@router.post("/login", response_model=LoginResponse)
async def login_for_access_token(
    login_data: LoginRequest, db: AsyncSession = Depends(get_db)
):
    """Login tradicional con email y contraseña para acceder al panel web."""
    stmt = select(User).where(User.email == login_data.email)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas (Usuario no encontrado)",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if user.status != UserStatus.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El usuario no está activo o ha sido bloqueado.",
        )
        
    if not user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Este usuario no tiene contraseña web asignada. Solicite restablecimiento al Administrador.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Contraseña incorrecta",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return _build_token_and_user(user)


# ─── Endpoint 2: Auth Telegram / Sonia (Híbrido) ─────────────────────────────

@router.post("/telegram", response_model=LoginResponse)
async def telegram_auth(
    auth_data: TelegramAuthRequest,
    db: AsyncSession = Depends(get_db),
    x_sonia_secret: Optional[str] = Header(None),
):
    """
    Endpoint exclusivo para Sonia (el bot).
    Sonia llama a este endpoint cuando un usuario de Telegram interactúa.
    
    Lógica:
    1. Si el telegram_id ya está vinculado a un usuario activo → devuelve su JWT.
    2. Si no existe → crea un usuario provisional (pending) y devuelve el JWT.
       El superadmin puede aprobarlo desde la pantalla de 'Personal & Acceso'.
    
    Protección: requiere el header X-Sonia-Secret para evitar acceso externo.
    """
    # Validación del secreto del bot
    if x_sonia_secret != settings.SONIA_BOT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso no autorizado. Este endpoint es exclusivo del sistema Sonia."
        )

    # 1. Buscar usuario por telegram_id
    stmt = select(User).where(User.telegram_id == auth_data.telegram_id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if user:
        # Usuario ya existe → devolver su JWT (aunque esté pending, Sonia puede seguir funcionando)
        # Solo bloquear si fue explícitamente rechazado
        if user.status == UserStatus.rejected:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Este usuario ha sido bloqueado por el administrador."
            )
        return _build_token_and_user(user)

    # 2. Usuario nuevo → crear cuenta provisional vinculada al Telegram ID
    new_user = User(
        name=auth_data.name or f"Usuario Telegram {auth_data.telegram_id[-4:]}",
        telegram_id=auth_data.telegram_id,
        phone=auth_data.phone,
        role=Role.technician,     # Rol por defecto conservador
        status=UserStatus.pending, # Pendiente de aprobación del admin web
        tenant_id=None,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return _build_token_and_user(new_user)


# ─── Endpoint 3: Vincular Telegram a usuario Web existente ────────────────────

@router.post("/link-telegram", status_code=status.HTTP_200_OK)
async def link_telegram_to_user(
    link_data: TelegramLinkRequest,
    db: AsyncSession = Depends(get_db),
    x_sonia_secret: Optional[str] = Header(None),
):
    """
    Vincula un telegram_id a un usuario web ya creado.
    Útil cuando el admin crea el usuario en la web y luego el técnico
    interactúa con Sonia por primera vez.
    """
    if x_sonia_secret != settings.SONIA_BOT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso no autorizado."
        )

    import uuid as _uuid
    try:
        uid = _uuid.UUID(link_data.user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="user_id inválido")

    # Verificar si el telegram_id ya está en uso
    stmt_check = select(User).where(
        User.telegram_id == link_data.telegram_id
    )
    existing = (await db.execute(stmt_check)).scalar_one_or_none()
    if existing and str(existing.id) != link_data.user_id:
        raise HTTPException(
            status_code=409,
            detail=f"El telegram_id ya está vinculado al usuario '{existing.name}'."
        )

    stmt = select(User).where(User.id == uid)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    user.telegram_id = link_data.telegram_id
    await db.commit()

    return {
        "message": f"Telegram ID vinculado exitosamente al usuario '{user.name}'.",
        "user_id": str(user.id),
        "telegram_id": link_data.telegram_id
    }


# ─── Endpoint 4: Consulta de usuario por Telegram (para Sonia) ───────────────

@router.get("/telegram/{telegram_id}")
async def get_user_by_telegram(
    telegram_id: str,
    db: AsyncSession = Depends(get_db),
    x_sonia_secret: Optional[str] = Header(None),
):
    """
    Permite a Sonia consultar si un telegram_id ya tiene cuenta,
    cuál es su rol y a qué taller pertenece, sin generar token.
    """
    if x_sonia_secret != settings.SONIA_BOT_SECRET:
        raise HTTPException(status_code=403, detail="Acceso no autorizado.")

    stmt = select(User).where(User.telegram_id == telegram_id)
    user = (await db.execute(stmt)).scalar_one_or_none()

    if not user:
        return {"exists": False, "telegram_id": telegram_id}

    return {
        "exists": True,
        "user_id": str(user.id),
        "name": user.name,
        "role": user.role.value,
        "status": user.status.value,
        "tenant_id": str(user.tenant_id) if user.tenant_id else None,
    }
