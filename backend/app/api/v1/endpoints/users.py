from fastapi import APIRouter, Depends, HTTPException, status, Header
from typing import List, Optional
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.user import User, UserStatus, Role
from app.schemas.user import UserCreate, UserOut, UserStatusUpdate, UserUpdate
from app.api.deps import get_current_user, get_optional_user, CurrentUser
from uuid import UUID
from app.config import settings

router = APIRouter()

@router.post("/", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
    x_sonia_secret: Optional[str] = Header(None),
    current_user: Optional[CurrentUser] = Depends(get_optional_user),
):
    """
    Crea un nuevo usuario.
    - Con X-Sonia-Secret: uso interno del bot (crea clientes durante la recepción).
    - Con Bearer JWT: Solo SuperAdmin o Admin del panel web.
    """
    is_bot_call = x_sonia_secret == settings.SONIA_BOT_SECRET

    if not is_bot_call:
        if not current_user or not current_user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene permisos para crear usuarios."
            )

    # Idempotencia: si ya existe ese telegram_id, devolver el existente
    if user_in.telegram_id:
        stmt = select(User).where(User.telegram_id == user_in.telegram_id)
        existing_user = (await db.execute(stmt)).scalar_one_or_none()
        if existing_user:
            return existing_user

    new_user = User(**user_in.model_dump())

    # Si viene via JWT de un Admin (no superadmin), forzar su tenant
    if not is_bot_call and current_user and not current_user.is_superadmin:
        new_user.tenant_id = current_user.tenant_id

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user


@router.get("/", response_model=List[UserOut])
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Lista usuarios según el rol:
    - SuperAdmin: Ve todos los usuarios de la red.
    - Admin: Ve solo los usuarios de su mismo taller (tenant).
    """
    stmt = select(User)
    if not current_user.is_superadmin:
        stmt = stmt.where(User.tenant_id == current_user.tenant_id)
        
    result = await db.execute(stmt)
    return result.scalars().all()

@router.get("/telegram/{telegram_id}", response_model=UserOut)
async def get_user_by_telegram_id(
    telegram_id: str, 
    db: AsyncSession = Depends(get_db),
    x_sonia_secret: Optional[str] = Header(None)
):
    """
    OBSOLETO: Usar /auth/telegram/{telegram_id} en su lugar.
    Mantenido por compatibilidad temporal con el bot.
    Requiere el secreto de Sonia.
    """
    if x_sonia_secret != settings.SONIA_BOT_SECRET:
        raise HTTPException(status_code=403, detail="Acceso no autorizado.")
        
    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no registrado en la red")
    
    if user.status != UserStatus.active:
        raise HTTPException(status_code=403, detail=f"Usuario en estado {user.status.value}, contacte al administrador")
    
    return user

@router.get("/superadmins/telegram-ids", response_model=List[str])
async def get_superadmin_telegram_ids(
    db: AsyncSession = Depends(get_db),
    x_sonia_secret: Optional[str] = Header(None)
):
    """
    Devuelve la lista de telegram_ids de superadmins activos.
    Solo para uso interno del bot Sonia.
    """
    if x_sonia_secret != settings.SONIA_BOT_SECRET:
        raise HTTPException(status_code=403, detail="Acceso no autorizado.")
    stmt = select(User).where(
        User.role == Role.superadmin,
        User.status == UserStatus.active,
        User.telegram_id.isnot(None)
    )
    result = await db.execute(stmt)
    users = result.scalars().all()
    return [u.telegram_id for u in users if u.telegram_id]


@router.get("/pending", response_model=List[UserOut])
async def get_pending_users(
    db: AsyncSession = Depends(get_db),
    x_sonia_secret: Optional[str] = Header(None),
    current_user: Optional[CurrentUser] = Depends(get_optional_user),
):
    """
    Obtiene la lista de usuarios en estado 'pending'.
    - Con X-Sonia-Secret: uso interno del bot (ve todos los pendientes).
    - Con Bearer JWT: SuperAdmin ve todos; Admin solo ve los de su taller.
    """
    is_bot_call = x_sonia_secret == settings.SONIA_BOT_SECRET

    if not is_bot_call and not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado.")
    if not is_bot_call and not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin permisos.")

    stmt = select(User).where(
        User.status == UserStatus.pending,
        User.role != Role.client  # los clientes no pasan por aprobación manual
    )
    if not is_bot_call and not current_user.is_superadmin:
        stmt = stmt.where(User.tenant_id == current_user.tenant_id)

    result = await db.execute(stmt)
    return result.scalars().all()

@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: UUID,
    user_in: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Actualiza campos de un usuario. Solo superadmin."""
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Sin permisos")

    stmt = select(User).where(User.id == user_id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    for field, value in user_in.model_dump(exclude_unset=True).items():
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/{user_id}/status", response_model=UserOut)
async def update_user_status(
    user_id: UUID,
    status_update: UserStatusUpdate,
    db: AsyncSession = Depends(get_db),
    x_sonia_secret: Optional[str] = Header(None),
    current_user: Optional[CurrentUser] = Depends(get_optional_user),
):
    """
    Actualiza el estado de un usuario.
    Acepta JWT Bearer (panel web) o X-Sonia-Secret (bot Sonia).
    """
    is_bot_call = x_sonia_secret == settings.SONIA_BOT_SECRET

    if not is_bot_call and not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado.")
    if not is_bot_call and not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin permisos.")

    stmt = select(User).where(User.id == user_id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if not is_bot_call and not current_user.is_superadmin and user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="No tiene permisos sobre este usuario")
        
    user.status = status_update.status
    await db.commit()
    await db.refresh(user)
    
    return user
