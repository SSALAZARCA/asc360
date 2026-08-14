from fastapi import APIRouter, Depends, HTTPException, Query, status, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.future import select
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models.user import User, UserStatus, Role
from app.schemas.user import UserCreate, UserOut, UserStatusUpdate, UserUpdate
from app.core.security import get_password_hash, verify_sonia_secret
from app.api.deps import get_current_user, get_optional_user, CurrentUser
from uuid import UUID
import uuid
import io
import datetime
import openpyxl
from app.config import settings

router = APIRouter()

STATUS_LABELS = {
    UserStatus.active: "Activo",
    UserStatus.pending: "Pendiente",
    UserStatus.rejected: "Rechazado",
}

ROLE_LABELS = {
    Role.superadmin: "Super Admin",
    Role.jefe_taller: "Jefe de Taller",
    Role.technician: "Técnico",
    Role.client: "Cliente",
    Role.parts_dealer: "Distribuidor",
    Role.proveedor: "Proveedor",
    Role.administrativo: "Administrativo",
}


def _scoped_users_query(current_user: CurrentUser):
    """Same visibility rule shared by `list_users` and `export_users`:
    SuperAdmin sees every user network-wide, anyone else only their own
    tenant's. Kept in one place so the two callers can never diverge."""
    stmt = select(User)
    if not current_user.is_superadmin:
        stmt = stmt.where(User.tenant_id == current_user.tenant_id)
    return stmt


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
    is_bot_call = verify_sonia_secret(x_sonia_secret, settings.SONIA_BOT_SECRET)

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

    # Dedup de clientes por cédula (reception "moto nueva" flow): sin esto,
    # un cliente que ya existe -- con otra moto, o con una placa que no
    # coincidió -- se duplicaba en cada alta. No toca otros roles/llamadores
    # que no envían `identification`.
    if user_in.identification and user_in.role == Role.client:
        stmt = select(User).where(
            User.role == Role.client,
            User.identification == user_in.identification,
        )
        existing_client = (await db.execute(stmt)).scalar_one_or_none()
        if existing_client:
            # sdd/reception-email-notification Phase 7 (design ADR 8, bug
            # found during design): this dedup path used to return the
            # existing row WITHOUT ever applying the submitted payload, so
            # a "new client" who is really an existing client-by-cedula
            # had their freshly-captured email silently discarded.
            # Backfill ONLY when the stored email is empty/None; NEVER
            # overwrite a non-empty stored email with a request-body value
            # (BR1 -- also a security constraint: a request-body value
            # must never be able to silently redirect where another
            # client's PDF goes).
            if user_in.email and not (existing_client.email or "").strip():
                existing_client.email = user_in.email
                db.add(existing_client)
                await db.flush()
            return existing_client

    user_data = user_in.model_dump(exclude={"password"})
    new_user = User(**user_data)
    if user_in.password:
        new_user.hashed_password = get_password_hash(user_in.password)

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
    stmt = _scoped_users_query(current_user)
    result = await db.execute(stmt)
    return result.scalars().all()


def _build_users_workbook(users: list, scope: str) -> io.BytesIO:
    """Pure Excel-building step, split out from `export_users` so it can be
    unit-tested (openpyxl round-trip) without a DB/HTTP layer involved."""
    wb = openpyxl.Workbook()
    ws = wb.active

    if scope == "clients":
        ws.title = "Clientes"
        ws.append([
            "Nombre", "Cédula", "Teléfono", "Email", "Fecha de nacimiento",
            "Ciudad", "Departamento", "Dirección", "Estado", "Telegram Vinculado",
        ])
        for u in users:
            ws.append([
                u.name,
                u.identification or "",
                u.phone or "",
                u.email or "",
                str(u.birth_date) if u.birth_date else "",
                u.city or "",
                u.department or "",
                u.address or "",
                STATUS_LABELS.get(u.status, u.status.value if u.status else ""),
                "Sí" if u.telegram_id else "No",
            ])
    else:
        ws.title = "Usuarios del Sistema"
        ws.append(["Nombre", "Rol", "Email", "Teléfono", "Taller Asignado", "Estado", "Telegram Vinculado"])
        for u in users:
            taller = u.service_center_name or (u.tenant.name if u.tenant else None) or "Acceso Global"
            ws.append([
                u.name,
                ROLE_LABELS.get(u.role, u.role.value if u.role else ""),
                u.email or "",
                u.phone or "",
                taller,
                STATUS_LABELS.get(u.status, u.status.value if u.status else ""),
                "Sí" if u.telegram_id else "No",
            ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


@router.get("/export")
async def export_users(
    scope: str = Query(..., pattern="^(clients|staff)$"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Excel export mirroring `list_users`'s exact visibility scope
    (`_scoped_users_query`) -- a non-superadmin only ever exports their own
    tenant's users, same as the on-screen table.

    `scope=clients` -> only `role=client` rows, full client PII columns
    (cédula, ciudad, etc.). `scope=staff` -> every other role, system-access
    columns (rol, taller asignado) instead."""
    stmt = _scoped_users_query(current_user).options(selectinload(User.tenant))
    if scope == "clients":
        stmt = stmt.where(User.role == Role.client)
    else:
        stmt = stmt.where(User.role != Role.client)

    users = (await db.execute(stmt)).scalars().all()
    buf = _build_users_workbook(users, scope)

    filename_prefix = "clientes" if scope == "clients" else "usuarios_sistema"
    filename = f"{filename_prefix}_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
    if not verify_sonia_secret(x_sonia_secret, settings.SONIA_BOT_SECRET):
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
    if not verify_sonia_secret(x_sonia_secret, settings.SONIA_BOT_SECRET):
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
    is_bot_call = verify_sonia_secret(x_sonia_secret, settings.SONIA_BOT_SECRET)

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


class PasswordReset(BaseModel):
    password: str


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Elimina un usuario. Solo superadmin. No puede eliminarse a sí mismo."""
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Sin permisos")
    if str(current_user.user_id) == str(user_id):
        raise HTTPException(status_code=400, detail="No podés eliminarte a vos mismo")

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    from app.models.order import ServiceOrder, OrderHistory
    from app.models.imports import PackingList, ReconciliationResult, ImportAttachment, ImportAuditLog
    from app.models.logistics import PartsOrder

    # Nullificar FKs nullable antes de eliminar
    for model, cols in [
        (ServiceOrder, ["client_id", "technician_id"]),
        (OrderHistory, ["changed_by"]),
        (PackingList, ["uploaded_by"]),
        (ReconciliationResult, ["confirmed_by"]),
        (ImportAttachment, ["uploaded_by"]),
        (ImportAuditLog, ["actor_id"]),
    ]:
        for col in cols:
            await db.execute(
                sql_update(model).where(getattr(model, col) == user_id).values({col: None})
            )

    # parts_orders.created_by es NOT NULL — reasignar al superadmin que ejecuta la acción
    await db.execute(
        sql_update(PartsOrder)
        .where(PartsOrder.created_by == user_id)
        .values({"created_by": uuid.UUID(current_user.user_id)})
    )

    await db.delete(user)
    await db.commit()


@router.patch("/{user_id}/password", status_code=204)
async def reset_user_password(
    user_id: UUID,
    payload: PasswordReset,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Resetea la contraseña web de un usuario. Solo superadmin."""
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Sin permisos")

    stmt = select(User).where(User.id == user_id)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    user.hashed_password = get_password_hash(payload.password)
    await db.commit()


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
    is_bot_call = verify_sonia_secret(x_sonia_secret, settings.SONIA_BOT_SECRET)

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
