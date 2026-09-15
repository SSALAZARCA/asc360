"""
Motored Pedidos — router de usuarios (sdd/motored-pedidos-cimientos,
Fase 4). El único maestro NO cubierto por `services/maestros.py` (esa capa
cubre proveedor/sucursal/bodega/referencia únicamente) -- este router opera
DIRECTAMENTE sobre el modelo `Usuario`, replicando el mismo patrón
soft-delete-only + auditoría (`services/auditoria.py`) que el resto del
módulo usa para maestros.

ADMIN únicamente en los 4 verbos -- crear/leer/desactivar usuarios de
Motored es en sí misma una operación administrativa (spec 'RBAC role
enforcement').
"""
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.motored.deps import MotoredUser, get_motored_db_or_503, require_motored_ready, require_roles
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.models.usuario_sucursal import UsuarioSucursal
from app.motored.schemas.usuario import UsuarioCreate, UsuarioRead
from app.motored.services import auditoria

router = APIRouter(
    prefix="/usuarios",
    tags=["motored-usuarios"],
    dependencies=[Depends(require_motored_ready)],
)

_require_admin = require_roles("ADMIN")


def _to_read(usuario: Usuario) -> dict:
    return UsuarioRead.model_validate(usuario).model_dump(mode="json")


async def _get_or_404(db: AsyncSession, usuario_id: uuid.UUID) -> Usuario:
    result = await db.execute(select(Usuario).where(Usuario.id == usuario_id))
    usuario = result.scalars().first()
    if usuario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    return usuario


@router.get("")
async def list_usuarios(
    db: AsyncSession = Depends(get_motored_db_or_503),
    _user: MotoredUser = Depends(_require_admin),
) -> List[dict]:
    result = await db.execute(select(Usuario))
    return [_to_read(u) for u in result.scalars().all()]


@router.get("/{usuario_id}")
async def get_usuario(
    usuario_id: uuid.UUID,
    db: AsyncSession = Depends(get_motored_db_or_503),
    _user: MotoredUser = Depends(_require_admin),
) -> dict:
    usuario = await _get_or_404(db, usuario_id)
    return _to_read(usuario)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_usuario(
    payload: UsuarioCreate,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_admin),
) -> dict:
    try:
        role = MotoredRole(payload.role)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Rol desconocido: '{payload.role}'",
        )

    usuario = Usuario(
        id=uuid.uuid4(),
        nombre=payload.nombre,
        email=payload.email,
        hashed_password=get_password_hash(payload.password),
        role=role,
        activo=True,
    )
    db.add(usuario)
    for sucursal_id in payload.sucursal_ids:
        db.add(UsuarioSucursal(id=uuid.uuid4(), usuario_id=usuario.id, sucursal_id=sucursal_id))

    auditoria.audit_create(db, "usuario", usuario.id, uuid.UUID(user.user_id))
    await db.commit()
    return _to_read(usuario)


@router.delete("/{usuario_id}")
async def deactivate_usuario(
    usuario_id: uuid.UUID,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_admin),
) -> dict:
    """Soft-delete ÚNICAMENTE (`activo = false`) -- jamás un DELETE SQL
    real, mismo patrón que el resto del módulo aplica a los maestros."""
    usuario = await _get_or_404(db, usuario_id)
    usuario.activo = False
    auditoria.audit_deactivate(db, "usuario", usuario.id, uuid.UUID(user.user_id))
    await db.commit()
    return _to_read(usuario)
