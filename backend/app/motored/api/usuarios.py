"""
Motored Pedidos — router de usuarios (sdd/motored-pedidos-cimientos,
Fase 4). El único maestro NO cubierto por `services/maestros.py` (esa capa
cubre proveedor/sucursal/bodega/referencia únicamente) -- este router opera
DIRECTAMENTE sobre el modelo `Usuario`, replicando el mismo patrón
soft-delete-only + auditoría (`services/auditoria.py`) que el resto del
módulo usa para maestros.

ADMIN únicamente en los 4 verbos originales -- crear/leer/desactivar
usuarios de Motored es en sí misma una operación administrativa (spec
'RBAC role enforcement').

sdd/motored-ventas-perdidas-bot, Phase 4 "Approval service + Usuarios UI"
(design D5) agrega:
- `GET /usuarios?status=pending` -- lista de solicitudes de auto-registro
  del bot Lore pendientes de resolver (`ASESOR_MOSTRADOR`, `status=
  'pending'`).
- `POST /usuarios/{id}/aprobar|rechazar` -- delegan en
  `services/solicitudes.py::resolver_solicitud`, la MISMA función que la
  Fase 5 hará llamar desde los botones inline del bot -- nunca una
  segunda implementación de la transición acá.
- `POST /usuarios/me/telegram/codigo` | `DELETE /usuarios/me/telegram` --
  vinculación de Telegram de un ADMIN para notificaciones push, siempre
  sobre SU PROPIA fila (nunca la de otro usuario -- spec "ADMIN
  telegram-linking independent of role").
"""
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.motored.deps import MotoredUser, get_motored_db_or_503, require_motored_ready, require_roles
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.models.usuario_sucursal import UsuarioSucursal
from app.motored.schemas.usuario import UsuarioCreate, UsuarioRead
from app.motored.services import auditoria, solicitudes, vinculacion

router = APIRouter(
    prefix="/usuarios",
    tags=["motored-usuarios"],
    dependencies=[Depends(require_motored_ready)],
)

_require_admin = require_roles("ADMIN")


def _to_read(usuario: Usuario) -> dict:
    payload = UsuarioRead.model_validate(usuario).model_dump(mode="json")
    # `telegram_vinculado` no tiene atributo homónimo en `Usuario` (design
    # D5: el `telegram_id` crudo nunca se expone) -- se deriva acá, después
    # de `model_validate`, en vez de vía `from_attributes`.
    payload["telegram_vinculado"] = usuario.telegram_id is not None
    return payload


async def _get_or_404(db: AsyncSession, usuario_id: uuid.UUID) -> Usuario:
    result = await db.execute(select(Usuario).where(Usuario.id == usuario_id))
    usuario = result.scalars().first()
    if usuario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    return usuario


@router.get("")
async def list_usuarios(
    status_filtro: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_motored_db_or_503),
    _user: MotoredUser = Depends(_require_admin),
) -> List[dict]:
    """`?status=pending` (sdd/motored-ventas-perdidas-bot, task 4.3) es el
    listado que la pantalla Usuarios usa para mostrar las solicitudes de
    auto-registro del bot Lore todavía sin resolver. Sin el parámetro,
    comportamiento IDÉNTICO al de hoy (todos los usuarios, sin filtrar).

    Post-Phase-4 review (finding #5): cuando SÍ se filtra por `status`,
    también se exige `activo` -- un asesor `pending` desactivado (`DELETE
    /usuarios/{id}`) no debe seguir apareciendo en la lista de solicitudes
    con botones Aprobar/Rechazar vivos (que igual devolverían 409, ya que
    el propio claim de `resolver_solicitud` exige `activo`). Deliberadamente
    NO se agrega este guard cuando no hay filtro, para no tocar el
    comportamiento sin filtrar de hoy."""
    stmt = select(Usuario)
    if status_filtro is not None:
        stmt = stmt.where(Usuario.status == status_filtro, Usuario.activo.is_(True))
    result = await db.execute(stmt)
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


async def _resolver_solicitud_endpoint(
    db: AsyncSession, usuario_id: uuid.UUID, decision: str, user: MotoredUser
) -> dict:
    """Compartido por `/aprobar` y `/rechazar` -- ambos difieren únicamente
    en el literal `decision` que pasan. Delega TODA la lógica de
    transición en `services/solicitudes.py::resolver_solicitud` (design
    D5: la misma función que la Fase 5 hará llamar desde los botones
    inline del bot) y traduce su `SolicitudYaResuelta` al mismo 409 que
    `anular_carga` ya usa para `CargaYaAnuladaError` -- mismo criterio en
    todo el módulo."""
    try:
        usuario = await solicitudes.resolver_solicitud(
            db, usuario_id, decision, uuid.UUID(user.user_id)
        )
    except solicitudes.SolicitudYaResuelta as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    auditoria.diff_and_audit(
        db, "usuario", usuario_id, uuid.UUID(user.user_id),
        before={"status": "pending"}, after={"status": decision},
    )
    await db.commit()
    return _to_read(usuario)


@router.post("/{usuario_id}/aprobar")
async def aprobar_usuario(
    usuario_id: uuid.UUID,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_admin),
) -> dict:
    return await _resolver_solicitud_endpoint(db, usuario_id, "approved", user)


@router.post("/{usuario_id}/rechazar")
async def rechazar_usuario(
    usuario_id: uuid.UUID,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_admin),
) -> dict:
    return await _resolver_solicitud_endpoint(db, usuario_id, "rejected", user)


@router.post("/me/telegram/codigo")
async def generar_codigo_telegram(
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_admin),
) -> dict:
    """Genera un código de vinculación de un solo uso para la PROPIA fila
    del ADMIN autenticado (nunca la de otro usuario -- design D5, spec
    "ADMIN telegram-linking independent of role"). El código se muestra
    UNA sola vez acá; solo su hash queda persistido
    (`services/vinculacion.py::generar_codigo_vinculacion`)."""
    usuario = await _get_or_404(db, uuid.UUID(user.user_id))
    codigo = await vinculacion.generar_codigo_vinculacion(db, usuario)
    await db.commit()
    return {"codigo": codigo, "expira_en": usuario.codigo_vinculacion_expira.isoformat()}


@router.delete("/me/telegram")
async def desvincular_telegram(
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_admin),
) -> dict:
    """Desvincula el `telegram_id` de la PROPIA fila del ADMIN autenticado
    -- deja de recibir notificaciones push, sin afectar su rol ni sus
    permisos existentes."""
    usuario = await _get_or_404(db, uuid.UUID(user.user_id))
    usuario.telegram_id = None
    await db.commit()
    return _to_read(usuario)
