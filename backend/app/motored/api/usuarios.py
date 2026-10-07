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
- `POST /usuarios/me/telegram/codigo` | `GET|DELETE /usuarios/me/telegram` --
  vinculación de Telegram de un ADMIN o COMPRAS para notificaciones push, siempre
  sobre SU PROPIA fila (nunca la de otro usuario -- spec "ADMIN
  telegram-linking independent of role").

odd/motored-reporte-diario-asesor (T1) agrega la cédula del usuario, su
vínculo con el maestro de Vendedores: `PUT|DELETE /usuarios/{id}/cedula` y
`POST /usuarios/{id}/cedula/aprobar|rechazar` (ADMIN, auditados con la
cédula enmascarada). Las reglas viven en `services/cedula_usuario.py`.

odd/motored-reporte-diario-asesor (T3a) agrega el enlace personal del
informe: `GET|POST|DELETE /usuarios/{id}/enlace-informe` (ADMIN). POST
genera uno nuevo (anula el anterior) y Lore se lo envía al asesor; si el
envío falla, todo se revierte. Ninguna respuesta, auditoría ni log lleva el
token ni la URL. Desactivar al usuario, cambiar o quitar su cédula, o
desvincular su Telegram anulan el enlace activo
(`services/reporte_asesor_link.py::revocar_si_cambio`).

odd/motored-salir-y-cambio-password agrega `POST /usuarios/{id}/password`
(ADMIN fija una contraseña nueva a un usuario con acceso web) y exige un
largo mínimo de contraseña también al crear usuarios.
"""
import uuid
from datetime import date, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import get_password_hash
from app.motored.deps import MotoredUser, get_motored_db_or_503, require_motored_ready, require_roles
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.models.usuario_sucursal import UsuarioSucursal
from app.motored.schemas.usuario import (
    UsuarioCedulaUpdate, UsuarioCreate, UsuarioPasswordReset, UsuarioRead,
)
from app.motored.services import (
    auditoria, avisos_telegram, cedula_usuario, login_bloqueo, login_eventos,
    reporte_asesor_link, solicitudes, vinculacion,
)
from app.motored.services.password_policy import aplicar_password, validar_password

router = APIRouter(
    prefix="/usuarios",
    tags=["motored-usuarios"],
    dependencies=[Depends(require_motored_ready)],
)

_require_admin = require_roles("ADMIN")
# Vincular el PROPIO Telegram: ADMIN y COMPRAS (el aviso anticipado de
# antigüedad de datos le llega a COMPRAS por el bot Lore).
_require_telegram_propio = require_roles("ADMIN", "COMPRAS")

PAGE_SIZE_DEFAULT = 50
PAGE_SIZE_MAX = 200


def _to_read(usuario: Usuario, en_maestro: Optional[bool] = None) -> dict:
    payload = UsuarioRead.model_validate(usuario).model_dump(mode="json")
    payload["cedula_aprobada"] = bool(usuario.cedula_aprobada)
    payload["cedula_en_maestro"] = en_maestro if usuario.cedula else None
    # `telegram_vinculado` no tiene atributo homónimo en `Usuario` (design
    # D5: el `telegram_id` crudo nunca se expone) -- se deriva acá, después
    # de `model_validate`, en vez de vía `from_attributes`.
    payload["telegram_vinculado"] = usuario.telegram_id is not None
    # Only while the lock is still in force; stored naive UTC, sent with its offset.
    until = login_bloqueo.bloqueado_hasta_vigente(usuario, login_bloqueo.ahora())
    payload["bloqueado_hasta"] = until.replace(tzinfo=timezone.utc).isoformat() if until else None
    return payload


async def _get_or_404(db: AsyncSession, usuario_id: uuid.UUID) -> Usuario:
    result = await db.execute(select(Usuario).where(Usuario.id == usuario_id))
    usuario = result.scalars().first()
    if usuario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    return usuario


def _tiene_acceso_web(usuario: Usuario) -> bool:
    """Un asesor de mostrador (Lore) o una fila sin email entra solo por el
    bot: no tiene credenciales web que resetear."""
    role = getattr(usuario.role, "value", usuario.role)
    return bool(usuario.email) and role != MotoredRole.ASESOR_MOSTRADOR.value


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
    usuarios = result.scalars().all()
    en_maestro = await cedula_usuario.cedulas_en_maestro(
        db, (u.cedula for u in usuarios))
    return [_to_read(u, u.cedula in en_maestro) for u in usuarios]


@router.get("/ingresos")
async def list_ingresos(
    desde: Optional[date] = Query(None, description="Día (hora de Colombia), inclusivo"),
    hasta: Optional[date] = Query(None, description="Día (hora de Colombia), inclusivo"),
    resultado: Optional[str] = Query(None, pattern="^(EXITO|FALLO|BLOQUEADO)$"),
    texto: Optional[str] = Query(None, max_length=255, description="El correo contiene este texto"),
    usuario_id: Optional[uuid.UUID] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX),
    db: AsyncSession = Depends(get_motored_db_or_503),
    _user: MotoredUser = Depends(_require_admin),
) -> dict:
    """Registro de ingresos (T10): cada intento de login, el más nuevo primero.
    Declarado ANTES de `/{usuario_id}` para que "ingresos" no se lea como id."""
    return await login_eventos.listar(
        db, page=page, page_size=page_size, desde=desde, hasta=hasta,
        resultado=resultado, texto=texto, usuario_id=usuario_id,
    )


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
    validar_password(payload.password, payload.email)
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
        must_change_password=True,
        role=role,
        activo=True,
    )
    await _cedula_al_crear(db, usuario, payload.cedula)
    db.add(usuario)
    for sucursal_id in payload.sucursal_ids:
        db.add(UsuarioSucursal(id=uuid.uuid4(), usuario_id=usuario.id, sucursal_id=sucursal_id))

    auditoria.audit_create(db, "usuario", usuario.id, uuid.UUID(user.user_id))
    await _commit_cedula(db)
    return _to_read(usuario, en_maestro=bool(usuario.cedula))


async def _cedula_al_crear(db, usuario: Usuario, cedula) -> None:
    """An optional cédula on create is an ADMIN entry: approved directly."""
    usuario.cedula_aprobada = False
    if cedula is None or not str(cedula).strip():
        return
    try:
        await cedula_usuario.fijar_por_admin(db, usuario, cedula)
    except (
        cedula_usuario.CedulaInvalida, cedula_usuario.CedulaDuplicada,
    ) as exc:
        raise _http_cedula(exc)


@router.post("/{usuario_id}/password")
async def reset_password_usuario(
    usuario_id: uuid.UUID,
    payload: UsuarioPasswordReset,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_admin),
) -> dict:
    """Un ADMIN fija una contraseña nueva para un usuario con acceso web
    (también la suya). Guarda solo el hash; la respuesta es el usuario sin
    contraseña y la auditoría registra el cambio sin valores."""
    usuario = await _get_or_404(db, usuario_id)
    validar_password(payload.password, usuario.email)
    if not _tiene_acceso_web(usuario):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="SIN_ACCESO_WEB: el usuario no tiene acceso web (sin email o asesor de mostrador)",
        )
    aplicar_password(usuario, payload.password, must_change=True)
    auditoria.audit_password_reset(db, "usuario", usuario.id, uuid.UUID(user.user_id))
    await db.commit()
    return _to_read(usuario)


@router.post("/{usuario_id}/desbloquear")
async def desbloquear_usuario(
    usuario_id: uuid.UUID,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_admin),
) -> dict:
    """Un ADMIN levanta el bloqueo por intentos fallidos sin cambiar la
    contraseña (un reset de contraseña también lo levanta)."""
    usuario = await _get_or_404(db, usuario_id)
    login_bloqueo.limpiar_bloqueo(usuario)
    auditoria.audit_desbloqueo(db, "usuario", usuario.id, uuid.UUID(user.user_id))
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
    antes = reporte_asesor_link.huella(usuario)
    usuario.activo = False
    await reporte_asesor_link.revocar_si_cambio(db, usuario, antes)
    auditoria.audit_deactivate(db, "usuario", usuario.id, uuid.UUID(user.user_id))
    await db.commit()
    return _to_read(usuario)


@router.post("/{usuario_id}/reactivar")
async def reactivar_usuario(
    usuario_id: uuid.UUID,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_admin),
) -> dict:
    """Inverso de `deactivate_usuario`: solo `activo = true`, jamás `status`
    (un usuario `pending`/`rejected` sigue igual). Sin efecto si ya estaba
    activo."""
    usuario = await _get_or_404(db, usuario_id)
    if not usuario.activo:
        usuario.activo = True
        auditoria.audit_reactivate(db, "usuario", usuario.id, uuid.UUID(user.user_id))
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


def _estado_cedula(usuario: Usuario) -> dict:
    """Audit snapshot: the cédula is personal data, only its last 4."""
    return {
        "cedula": cedula_usuario.enmascarar(usuario.cedula),
        "cedula_aprobada": bool(usuario.cedula_aprobada),
    }


def _http_cedula(exc: Exception) -> HTTPException:
    codigo = (
        status.HTTP_422_UNPROCESSABLE_ENTITY
        if isinstance(exc, cedula_usuario.CedulaInvalida)
        else status.HTTP_409_CONFLICT
    )
    return HTTPException(status_code=codigo, detail=str(exc))


async def _cambiar_cedula(db, usuario_id, user, cambio) -> dict:
    """Shared by the 4 cédula endpoints: run `cambio(usuario)` (may raise a
    `cedula_usuario` error), audit the diff, commit."""
    usuario = await _get_or_404(db, usuario_id)
    antes = _estado_cedula(usuario)
    huella = reporte_asesor_link.huella(usuario)
    try:
        await cambio(usuario)
    except (
        cedula_usuario.CedulaInvalida, cedula_usuario.CedulaDuplicada,
        cedula_usuario.CedulaSinPendiente,
    ) as exc:
        raise _http_cedula(exc)
    await reporte_asesor_link.revocar_si_cambio(db, usuario, huella)
    auditoria.diff_and_audit(
        db, "usuario", usuario.id, uuid.UUID(user.user_id),
        before=antes, after=_estado_cedula(usuario),
    )
    await _commit_cedula(db)
    return _to_read(usuario, en_maestro=bool(usuario.cedula_aprobada))


async def _commit_cedula(db) -> None:
    """Commit; a racing approval of the same cédula hits the partial
    unique index and becomes the same clean 409."""
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if not cedula_usuario.es_choque_unico(exc):
            raise
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=cedula_usuario.MSG_CHOQUE,
        )


@router.put("/{usuario_id}/cedula")
async def fijar_cedula(
    usuario_id: uuid.UUID,
    payload: UsuarioCedulaUpdate,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_admin),
) -> dict:
    """ADMIN set/edit: validated and approved directly."""
    async def cambio(usuario):
        await cedula_usuario.fijar_por_admin(db, usuario, payload.cedula)
    return await _cambiar_cedula(db, usuario_id, user, cambio)


@router.post("/{usuario_id}/cedula/aprobar")
async def aprobar_cedula(
    usuario_id: uuid.UUID,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_admin),
) -> dict:
    """Approve the cédula an asesor typed in Lore."""
    async def cambio(usuario):
        await cedula_usuario.aprobar(db, usuario)
    return await _cambiar_cedula(db, usuario_id, user, cambio)


@router.post("/{usuario_id}/cedula/rechazar")
async def rechazar_cedula(
    usuario_id: uuid.UUID,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_admin),
) -> dict:
    """Reject a PENDING cédula: it is cleared."""
    async def cambio(usuario):
        cedula_usuario.rechazar(usuario)
    return await _cambiar_cedula(db, usuario_id, user, cambio)


@router.delete("/{usuario_id}/cedula")
async def quitar_cedula(
    usuario_id: uuid.UUID,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_admin),
) -> dict:
    """Clear the cédula, approved or pending."""
    async def cambio(usuario):
        cedula_usuario.quitar(usuario)
    return await _cambiar_cedula(db, usuario_id, user, cambio)


@router.post("/me/telegram/codigo")
async def generar_codigo_telegram(
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_telegram_propio),
) -> dict:
    """Genera un código de vinculación de un solo uso para la PROPIA fila
    del ADMIN o COMPRAS autenticado (nunca la de otro usuario -- design D5, spec
    "ADMIN telegram-linking independent of role"). El código se muestra
    UNA sola vez acá; solo su hash queda persistido
    (`services/vinculacion.py::generar_codigo_vinculacion`)."""
    usuario = await _get_or_404(db, uuid.UUID(user.user_id))
    codigo = await vinculacion.generar_codigo_vinculacion(db, usuario)
    await db.commit()
    return {"codigo": codigo, "expira_en": usuario.codigo_vinculacion_expira.isoformat()}


@router.get("/me/telegram")
async def estado_telegram(
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_telegram_propio),
) -> dict:
    """Si la PROPIA fila ya tiene un Telegram vinculado (nunca el id)."""
    usuario = await _get_or_404(db, uuid.UUID(user.user_id))
    return {"telegram_vinculado": usuario.telegram_id is not None}


@router.delete("/me/telegram")
async def desvincular_telegram(
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_telegram_propio),
) -> dict:
    """Desvincula el `telegram_id` de la PROPIA fila del usuario autenticado
    (ADMIN o COMPRAS) -- deja de recibir notificaciones push, sin afectar su rol ni sus
    permisos existentes."""
    usuario = await _get_or_404(db, uuid.UUID(user.user_id))
    antes = reporte_asesor_link.huella(usuario)
    usuario.telegram_id = None
    await reporte_asesor_link.revocar_si_cambio(db, usuario, antes)
    await db.commit()
    return _to_read(usuario)


# --- Enlace personal del informe (odd/motored-reporte-diario-asesor, T3a) --

MSG_SIN_LORE = (
    "Falta configurar LORE_BOT_TOKEN: no se puede enviar el enlace por Lore.")
MSG_ENVIO_FALLIDO = (
    "No se pudo enviar el enlace por Lore. El enlace anterior sigue igual.")
MSG_CHOQUE_ENLACE = (
    "Otro administrador generó un enlace para este usuario al mismo tiempo. "
    "Recarga la pantalla e intenta de nuevo.")


def _http(codigo: int, detalle: str) -> HTTPException:
    return HTTPException(status_code=codigo, detail=detalle)


def _exigir_configuracion_envio() -> None:
    """Both settings are checked before any write."""
    if not (settings.LORE_BOT_TOKEN or "").strip():
        raise _http(status.HTTP_409_CONFLICT, MSG_SIN_LORE)
    try:
        reporte_asesor_link.base_publica()
    except reporte_asesor_link.FaltaConfiguracion as exc:
        raise _http(status.HTTP_409_CONFLICT, str(exc))


def _estado_enlace_auditoria(link) -> dict:
    """Audit snapshot: state and creation time, never the token."""
    estado = reporte_asesor_link.estado(link)
    return {
        "enlace_informe": "activo" if estado["activo"] else "sin enlace",
        "enlace_informe_creado_en": estado["creado_en"],
    }


async def _crear_enlace(db, usuario: Usuario, admin_id: uuid.UUID):
    """Generate and flush the new link (a racing ADMIN hits the partial
    unique index here, before anything is sent). Rolls back on error."""
    try:
        link = await reporte_asesor_link.generar_link(db, usuario, admin_id)
        await db.flush()
    except reporte_asesor_link.EnlaceNoPermitido as exc:
        await db.rollback()
        raise _http(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    except IntegrityError:
        await db.rollback()
        raise _http(status.HTTP_409_CONFLICT, MSG_CHOQUE_ENLACE)
    return link


async def _enviar_enlace(db, usuario: Usuario, link) -> None:
    """Lore delivers the link; on failure everything rolls back so the old
    link stays active. Neither the token nor the URL is logged."""
    texto = reporte_asesor_link.texto_mensaje(
        usuario.nombre, reporte_asesor_link.url_del_link(link.token))
    enviado = await avisos_telegram.enviar_mensaje(
        settings.LORE_BOT_TOKEN, usuario.telegram_id, texto)
    if not enviado:
        await db.rollback()
        raise _http(status.HTTP_502_BAD_GATEWAY, MSG_ENVIO_FALLIDO)


@router.get("/{usuario_id}/enlace-informe")
async def estado_enlace_informe(
    usuario_id: uuid.UUID,
    db: AsyncSession = Depends(get_motored_db_or_503),
    _user: MotoredUser = Depends(_require_admin),
) -> dict:
    """Whether the asesor has an active link, and its last access."""
    usuario = await _get_or_404(db, usuario_id)
    link = await reporte_asesor_link.link_activo(db, usuario.id)
    return reporte_asesor_link.estado(link)


@router.post("/{usuario_id}/enlace-informe")
async def generar_enlace_informe(
    usuario_id: uuid.UUID,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_admin),
) -> dict:
    """"Generar enlace nuevo": revoke the old link, create a new one and
    send it by Lore. Committed only after Telegram accepted it."""
    usuario = await _get_or_404(db, usuario_id)
    _exigir_configuracion_envio()
    anterior = await reporte_asesor_link.link_activo(db, usuario.id)
    antes = _estado_enlace_auditoria(anterior)
    admin_id = uuid.UUID(user.user_id)
    link = await _crear_enlace(db, usuario, admin_id)
    await _enviar_enlace(db, usuario, link)
    auditoria.diff_and_audit(
        db, "usuario", usuario.id, admin_id,
        before=antes, after=_estado_enlace_auditoria(link),
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise _http(status.HTTP_409_CONFLICT, MSG_CHOQUE_ENLACE)
    return reporte_asesor_link.estado(link)


@router.delete("/{usuario_id}/enlace-informe")
async def anular_enlace_informe(
    usuario_id: uuid.UUID,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_admin),
) -> dict:
    """"Anular enlace": revoke the active link, if any."""
    usuario = await _get_or_404(db, usuario_id)
    link = await reporte_asesor_link.link_activo(db, usuario.id)
    if link is None:
        return reporte_asesor_link.estado(None)
    await reporte_asesor_link.anular_link(
        db, usuario.id, reporte_asesor_link.MOTIVO_ANULADO)
    auditoria.diff_and_audit(
        db, "usuario", usuario.id, uuid.UUID(user.user_id),
        before={"enlace_informe": "activo"},
        after={"enlace_informe": "anulado"},
    )
    await db.commit()
    return reporte_asesor_link.estado(None)
