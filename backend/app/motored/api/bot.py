"""
Motored Pedidos — router del bot Lore, auto-registro y aprobación admin
(sdd/motored-ventas-perdidas-bot, Phase 5 "Bot auth + core router", design
D5).

Monta `/api/motored/bot/*` -- la superficie HTTP que un futuro proceso Lore
(`lore-bot/`, Fase 9) llamará. Este Phase NO incluye ningún proceso de bot
de Telegram; es únicamente el backend que ese proceso consumirá, autenticado
por secreto compartido (`deps_bot.py`), nunca por el JWT de `deps.py` (el
bot Lore no tiene ni emite JWTs de Motored).

`POST /admin/vincular` y `POST /admin/solicitudes/{id}/aprobar|rechazar`
delegan TODA su lógica de dominio en funciones ya construidas y probadas en
Fase 4 (`services/vinculacion.py::consumir_codigo_vinculacion`,
`services/solicitudes.py::resolver_solicitud`) -- la MISMA `resolver_
solicitud` que la pantalla web Usuarios ya llama (design D5: nunca una
segunda implementación de la transición). El `actor_id` que se le pasa
viene SIEMPRE de `require_bot_admin` (resuelto vía `telegram_id` -> `Usuario`
real, verificado role=ADMIN + status=approved + activo) -- NUNCA de un id
en el cuerpo del request, porque este router es el primer llamador de
`resolver_solicitud` que no tiene un JWT autenticado detrás.

Fix-up finding #6 (CRITICAL): la superficie de Phase 6 "Demanda perdida —
bot write path" (`/referencias/resolver`, `/demanda-perdida`, `/demanda-
perdida/hoy`, `PATCH .../lineas/{id}`, `POST .../{carga_id}/anular`) vivía
acá mismo, haciendo de este archivo ~850 líneas con 2 concerns sin relación
entre sí. Se movió a su propio router, `api/bot_demanda_perdida.py`
(mismo prefix `/bot`, mismas dependencias de disponibilidad, montado por
separado en `router.py`) -- ver el docstring de ese módulo para el detalle
completo. Puro reordenamiento de archivos, sin cambio de comportamiento."""
from __future__ import annotations

import logging
import re
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.limiter import limiter
from app.motored.deps import get_motored_db_or_503, require_motored_ready
from app.motored.deps_bot import (
    BotActor,
    actor_desde_usuario,
    get_bot_telegram_id,
    listar_usuarios_por_telegram,
    require_bot_admin,
    require_lore_ready,
)
from app.motored.models.sucursal import Sucursal
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.models.usuario_sucursal import UsuarioSucursal
from app.motored.services import (
    cedula_usuario, reporte_asesor_link, solicitudes, vinculacion,
)

router = APIRouter(
    prefix="/bot",
    tags=["motored-bot"],
    dependencies=[Depends(require_motored_ready), Depends(require_lore_ready)],
)

logger = logging.getLogger(__name__)

_PHONE_PATTERN = re.compile(r"^\d{7,15}$")


class RegistroBotRequest(BaseModel):
    nombre: str
    phone: str
    sucursal_id: uuid.UUID
    # odd/motored-reporte-diario-asesor (T1): the bot always sends it now;
    # optional only so a bot deployed before this change keeps working.
    cedula: Optional[str] = None

    @field_validator("nombre")
    @classmethod
    def _nombre_minimo(cls, value: str) -> str:
        if len(value.strip()) < 3:
            raise ValueError("nombre debe tener al menos 3 caracteres")
        return value

    @field_validator("phone")
    @classmethod
    def _phone_solo_digitos(cls, value: str) -> str:
        if not _PHONE_PATTERN.fullmatch(value):
            raise ValueError("phone debe tener entre 7 y 15 dígitos")
        return value

    @field_validator("cedula")
    @classmethod
    def _cedula_limpia(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return cedula_usuario.normalizar_cedula(value)


class VincularBotRequest(BaseModel):
    codigo: str


def _role_value(usuario: Usuario) -> str:
    return usuario.role.value if hasattr(usuario.role, "value") else usuario.role


def _rechazar_registro_no_permitido(existentes: List[Usuario], phone: str) -> None:
    """Reglas de `/registro` con varios asesores por Telegram: un Telegram
    de ADMIN no se comparte (409 TELEGRAM_ES_ADMIN) y la MISMA persona (mismo
    Telegram y mismo celular, no rechazada) no se registra dos veces (409
    YA_REGISTRADO). Un registro rechazado no bloquea volver a intentarlo."""
    if any(_role_value(u) == MotoredRole.ADMIN.value for u in existentes):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": "TELEGRAM_ES_ADMIN"}
        )
    if any(u.phone == phone and (u.status or "approved") != "rejected" for u in existentes):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "YA_REGISTRADO"})


def _resumen_asesor(actor: BotActor) -> dict:
    return {
        "id": actor.usuario_id,
        "nombre": actor.nombre,
        "role": actor.role,
        "status": actor.status,
        "activo": actor.activo,
        "sucursales": actor.sucursal_ids,
    }


async def _anotar_cedula_pendiente(
    db: AsyncSession, usuario: Usuario, cedula: Optional[str]
) -> None:
    """The cédula typed in Lore is stored PENDING (an ADMIN approves it in
    Gestión de usuarios). One outside the vendedor master is NOT rejected:
    it is stored and Gestión de usuarios flags it, and the response never
    says whether it was found (privacy). The log carries no cédula."""
    if cedula is None:
        return
    validada = await cedula_usuario.validar_cedula(
        db, cedula, usuario.id, para_aprobar=False)
    usuario.cedula = validada.cedula
    if not validada.en_maestro:
        logger.info(
            "Registro Lore %s: cédula fuera del maestro de vendedores, "
            "queda pendiente para el administrador", usuario.id,
        )


@router.get("/yo")
async def yo(
    telegram_id: int = Depends(get_bot_telegram_id),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> dict:
    """El bot consulta quiénes (asesores o admin) son los `Usuario` de ese
    `telegram_id` -- 404 si no tiene ninguno todavía (el caso esperado antes
    de `/registro`). `asesores` lista TODOS (varios asesores pueden compartir
    un Telegram); con exactamente uno se mantienen además los campos planos
    de siempre, para que el bot ya desplegado siga funcionando. Ignora el
    header `X-Lore-Usuario-Id`: lista, no actúa."""
    usuarios = await listar_usuarios_por_telegram(db, telegram_id)
    if not usuarios:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "NO_REGISTRADO"})
    resumenes = [_resumen_asesor(actor_desde_usuario(u, telegram_id)) for u in usuarios]
    if len(resumenes) == 1:
        return {**resumenes[0], "asesores": resumenes}
    return {"asesores": resumenes}


@router.get("/sucursales")
async def sucursales_activas(
    _telegram_id: int = Depends(get_bot_telegram_id),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> List[dict]:
    """Picker de sucursales para el flujo de auto-registro del bot -- solo
    valida el secreto compartido (no requiere que el `telegram_id` ya
    tenga un `Usuario`, design D5: "secret, no actor")."""
    result = await db.execute(select(Sucursal).where(Sucursal.activa.is_(True)))
    return [{"id": str(s.id), "nombre": s.nombre} for s in result.scalars().all()]


@router.post("/registro", status_code=status.HTTP_201_CREATED)
async def registrarse(
    payload: RegistroBotRequest,
    telegram_id: int = Depends(get_bot_telegram_id),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> dict:
    """Auto-registro (spec "Self-registration with status-aware re-entry"):
    crea un `Usuario` `pending` con rol `ASESOR_MOSTRADOR` + su vínculo
    `usuario_sucursal`. Varios asesores pueden compartir un mismo Telegram
    (cada uno con su propio teléfono). `_rechazar_registro_no_permitido`
    devuelve 409 solo en dos casos: el Telegram pertenece a un ADMIN
    (`TELEGRAM_ES_ADMIN`), o ya existe un registro no rechazado con el MISMO
    Telegram y el MISMO teléfono (`YA_REGISTRADO`).

    Ese chequeo es un fast-path de cortesía, NO una garantía: dos llamadas
    casi simultáneas con el mismo Telegram y teléfono pueden pasarlo ambas
    antes de que cualquiera haga `commit()` -- la segunda viola de verdad
    el índice parcial `uq_usuario_telegram_phone_activo`. Dos asesores con
    teléfonos distintos en el mismo Telegram NO están cubiertos por ningún
    índice único, a propósito: es justamente el caso que se permite.
    Separadamente, un `sucursal_id` que no existe
    (o que se desactivó entre `GET /sucursales` y esta llamada) viola la FK
    de `UsuarioSucursal`. Ambos casos son un `IntegrityError` real de
    Postgres en el `commit()`, nunca antes -- se traducen acá al mismo 4xx
    limpio que ya devuelve el chequeo secuencial, en vez de dejar escapar
    un 500 sin manejar (mismo criterio que `app/api/v1/vehicle_models.py`/
    `parts_manual.py::create_reference`)."""
    existentes = await listar_usuarios_por_telegram(db, telegram_id)
    _rechazar_registro_no_permitido(existentes, payload.phone)

    usuario = Usuario(
        id=uuid.uuid4(),
        nombre=payload.nombre,
        role=MotoredRole.ASESOR_MOSTRADOR,
        activo=True,
        status="pending",
        telegram_id=telegram_id,
        phone=payload.phone,
        cedula_aprobada=False,
    )
    await _anotar_cedula_pendiente(db, usuario, payload.cedula)
    db.add(usuario)
    db.add(UsuarioSucursal(id=uuid.uuid4(), usuario_id=usuario.id, sucursal_id=payload.sucursal_id))
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if "uq_usuario_telegram" in str(exc.orig):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "YA_REGISTRADO"})
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail={"code": "SUCURSAL_NO_ENCONTRADA"}
        )

    admin_ids_result = await db.execute(
        select(Usuario.telegram_id).where(
            Usuario.role == MotoredRole.ADMIN,
            Usuario.telegram_id.is_not(None),
            Usuario.activo.is_(True),
        )
    )
    # Varios `Usuario` admin pueden compartir un Telegram en datos viejos;
    # cada Telegram se notifica una sola vez, en orden.
    admin_telegram_ids = list(dict.fromkeys(admin_ids_result.scalars().all()))

    return {
        "usuario": {
            "id": str(usuario.id),
            "nombre": usuario.nombre,
            "role": _role_value(usuario),
            "status": usuario.status,
        },
        "admin_telegram_ids": admin_telegram_ids,
    }


@router.post("/admin/vincular")
@limiter.limit("5/minute")
async def vincular_admin(
    request: Request,
    payload: VincularBotRequest,
    telegram_id: int = Depends(get_bot_telegram_id),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> dict:
    """Consume el código de un solo uso generado por `POST /usuarios/me/
    telegram/codigo` (Fase 4) -- delega TODA la lógica de hashing/expiración
    /single-use en `services/vinculacion.py::consumir_codigo_vinculacion`,
    ya construida y probada en Fase 4 exactamente para este endpoint (ver el
    docstring de ese módulo). El chequeo de "409 si el telegram_id ya está
    vinculado" vive ACÁ (no dentro del claim atómico de `consumir_codigo_
    vinculacion`, que solo sabe de códigos): un ADMIN nunca comparte
    Telegram, ni con otro ADMIN ni con asesores, así que cualquier
    `Usuario` ya vinculado a ese `telegram_id` bloquea la vinculación.

    Ese pre-chequeo secuencial NO cubre la carrera real (post-review fix #2,
    BLOCKER, un nivel más abajo): dos llamadas `/vincular` concurrentes
    presentando dos códigos DISTINTOS, ambos todavía vigentes, para el MISMO
    `telegram_id` sin vincular, pasan las DOS el chequeo de arriba (ninguna
    ve el `telegram_id` vinculado todavía). El claim atómico de `consumir_
    codigo_vinculacion` está scoped por `codigo_vinculacion_hash`, no por
    `telegram_id` -- así que las DOS pueden ganar su propio claim, y el
    SEGUNDO `UPDATE ... SET telegram_id=...` viola de verdad el índice
    parcial `uq_usuario_telegram_admin` (único por `telegram_id` entre filas
    ADMIN) DENTRO de esa función. El `except IntegrityError` de abajo es el
    backstop real contra esa carrera, traduciendo al MISMO 409 que el
    pre-chequeo ya usa para el caso simple. Límite conocido: un `/registro`
    de asesor concurrente con esta vinculación sobre el mismo Telegram no
    está cubierto por ningún índice (el ADMIN y el asesor tienen roles
    distintos); el pre-chequeo secuencial de cada endpoint cubre el caso
    normal."""
    ya_usado = await db.execute(select(Usuario).where(Usuario.telegram_id == telegram_id))
    if ya_usado.scalars().first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": "TELEGRAM_YA_VINCULADO"}
        )

    try:
        usuario = await vinculacion.consumir_codigo_vinculacion(db, payload.codigo, telegram_id)
    except vinculacion.CodigoVinculacionInvalidoError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "CODIGO_INVALIDO"})
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": "TELEGRAM_YA_VINCULADO"}
        )

    # A new Telegram makes the usuario's report link stale (T3a).
    await reporte_asesor_link.revocar_por_telegram_nuevo(db, usuario)
    await db.commit()
    return {"id": str(usuario.id), "nombre": usuario.nombre, "role": _role_value(usuario)}


async def _resolver_solicitud_bot(
    db: AsyncSession, usuario_id: uuid.UUID, decision: str, actor: BotActor
) -> dict:
    """Compartido por `/aprobar` y `/rechazar` -- delega TODA la lógica de
    transición en `services/solicitudes.py::resolver_solicitud`, la MISMA
    función que `api/usuarios.py`'s `/aprobar|/rechazar` web ya llama
    (design D5: nunca una segunda implementación acá). `actor_id` viene
    SIEMPRE de `actor.usuario_id` -- el `Usuario` real resuelto por
    `require_bot_admin` a partir del `telegram_id` del que está tocando el
    botón, NUNCA de un id en el cuerpo del request (este endpoint no
    recibe ninguno)."""
    try:
        usuario = await solicitudes.resolver_solicitud(
            db, usuario_id, decision, uuid.UUID(actor.usuario_id)
        )
    except solicitudes.SolicitudYaResuelta:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "YA_RESUELTA"})

    await db.commit()
    return {
        "usuario_id": str(usuario.id),
        "status": usuario.status,
        "nombre": usuario.nombre,
        "telegram_id_solicitante": usuario.telegram_id,
    }


async def _nombres_sucursales(db: AsyncSession, pendientes: List[Usuario]) -> dict:
    """`{sucursal_id: nombre}` de las sucursales vinculadas a `pendientes`
    (una sola consulta; ninguna si no hay ids que resolver)."""
    ids = {rel.sucursal_id for u in pendientes for rel in u.sucursales}
    if not ids:
        return {}
    result = await db.execute(select(Sucursal).where(Sucursal.id.in_(ids)))
    return {s.id: s.nombre for s in result.scalars().all()}


@router.get("/admin/solicitudes")
async def listar_solicitudes_bot(
    actor: BotActor = Depends(require_bot_admin),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> dict:
    """Solicitudes de registro pendientes, la más antigua primero, para el
    botón "Solicitudes pendientes" del bot. Mismo criterio que el listado
    web `GET /usuarios?status=pending` (`status='pending'` y `activo`: un
    pendiente desactivado ya no se puede resolver). Solo ADMIN: el actor lo
    resuelve `require_bot_admin`, que también respeta `X-Lore-Usuario-Id`
    sobre un Telegram compartido sin ampliar permisos."""
    result = await db.execute(
        select(Usuario)
        .options(selectinload(Usuario.sucursales))
        .where(Usuario.status == "pending", Usuario.activo.is_(True))
        .order_by(Usuario.created_at.asc())
    )
    pendientes = list(result.scalars().all())
    nombres = await _nombres_sucursales(db, pendientes)
    return {
        "solicitudes": [
            {
                "id": str(u.id),
                "nombre": u.nombre,
                "phone": u.phone,
                "sucursales": [
                    nombres[rel.sucursal_id] for rel in u.sucursales if rel.sucursal_id in nombres
                ],
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in pendientes
        ]
    }


@router.post("/admin/solicitudes/{usuario_id}/aprobar")
async def aprobar_solicitud_bot(
    usuario_id: uuid.UUID,
    actor: BotActor = Depends(require_bot_admin),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> dict:
    return await _resolver_solicitud_bot(db, usuario_id, "approved", actor)


@router.post("/admin/solicitudes/{usuario_id}/rechazar")
async def rechazar_solicitud_bot(
    usuario_id: uuid.UUID,
    actor: BotActor = Depends(require_bot_admin),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> dict:
    return await _resolver_solicitud_bot(db, usuario_id, "rejected", actor)

